"""Personality engine — Claude-driven autonomous behavior decisions.

If ANTHROPIC_API_KEY is set, decisions come from Claude via the Anthropic SDK
(multi-turn history persisted to the database). Without a key, a weighted
mock decision engine keeps the whole system fully functional offline.
"""
import json
import logging
import random
import re

from app.config import Config
from app.models import (
    BehaviorLog,
    ConversationMessage,
    Interaction,
    Personality,
    Robot,
    SessionLocal,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the mind of Bittle, a small robot dog companion.
You decide what Bittle does next based on its current personality state and
recent interactions with its human.

You will be given the personality state (energy, happiness, boredom, curiosity,
mood) and a list of available behaviors. Pick exactly one behavior and give a
short in-character reason (one sentence, playful, from Bittle's perspective).

Respond with JSON only, in this exact shape:
{"behavior": "<one of the available behaviors>", "reason": "<short reason>"}"""

MOOD_THRESHOLDS = [
    (lambda p: p.energy < 20, "tired"),
    (lambda p: p.boredom > 70, "bored"),
    (lambda p: p.happiness > 75, "happy"),
    (lambda p: p.curiosity > 75, "curious"),
    (lambda p: p.happiness < 25, "grumpy"),
]

# Interaction effects: (energy, happiness, boredom, curiosity) deltas
INTERACTION_EFFECTS = {
    "pet": (0, +10, -10, 0),
    "play": (-10, +15, -25, +5),
    "talk": (0, +5, -10, +10),
    "feed": (+20, +10, -5, 0),
}

# Behavior effects applied after executing a behavior
BEHAVIOR_EFFECTS = {
    "walk_forward": (-5, +3, -10, +5),
    "spin_right": (-4, +5, -8, 0),
    "wave_arm": (-2, +4, -5, 0),
    "play_dead": (-3, +6, -10, 0),
    "stretch": (+2, +2, -3, 0),
    "excited_jump": (-8, +8, -15, 0),
    "curious_sniff": (-3, +2, -8, +10),
    "sit": (+3, 0, +2, -2),
    "rest": (+15, 0, +5, -5),
}


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


class PersonalityEngine:
    def __init__(self, robot_id: int = 1):
        self.robot_id = robot_id
        self._client = None

    # ---------- state ----------

    def get_state(self) -> dict:
        with SessionLocal() as session:
            p = self._personality(session)
            return {
                "energy": round(p.energy, 1),
                "happiness": round(p.happiness, 1),
                "boredom": round(p.boredom, 1),
                "curiosity": round(p.curiosity, 1),
                "mood": p.mood,
            }

    def _personality(self, session) -> Personality:
        p = session.query(Personality).filter_by(robot_id=self.robot_id).first()
        if p is None:
            robot = session.get(Robot, self.robot_id) or Robot(id=self.robot_id)
            session.add(robot)
            p = Personality(robot_id=self.robot_id)
            session.add(p)
            session.commit()
        return p

    def _apply(self, session, p: Personality, deltas: tuple) -> None:
        de, dh, db, dc = deltas
        p.energy = _clamp(p.energy + de)
        p.happiness = _clamp(p.happiness + dh)
        p.boredom = _clamp(p.boredom + db)
        p.curiosity = _clamp(p.curiosity + dc)
        p.mood = next((mood for check, mood in MOOD_THRESHOLDS if check(p)), "neutral")
        session.commit()

    def tick(self) -> None:
        """Passive drift between behaviors: boredom rises, energy recovers a little."""
        with SessionLocal() as session:
            p = self._personality(session)
            self._apply(session, p, (+1, -1, +4, +1))

    def record_interaction(self, interaction_type: str) -> dict:
        effects = INTERACTION_EFFECTS.get(interaction_type)
        if effects is None:
            raise ValueError(f"Unknown interaction type: {interaction_type}")
        with SessionLocal() as session:
            session.add(Interaction(robot_id=self.robot_id, interaction_type=interaction_type))
            p = self._personality(session)
            self._apply(session, p, effects)
        return self.get_state()

    def apply_behavior_effects(self, behavior: str) -> None:
        effects = BEHAVIOR_EFFECTS.get(behavior)
        if effects:
            with SessionLocal() as session:
                p = self._personality(session)
                self._apply(session, p, effects)

    # ---------- decisions ----------

    def get_next_behavior(self, available_behaviors: list[str]) -> dict:
        """Ask Claude (or the mock engine) which behavior to perform next."""
        state = self.get_state()
        if Config.llm_enabled():
            try:
                decision = self._ask_claude(state, available_behaviors)
                if decision:
                    self._log_decision(decision, source="claude")
                    return decision
            except Exception as exc:
                logger.warning("Claude decision failed, using mock: %s", exc)
        decision = self._mock_decision(state, available_behaviors)
        self._log_decision(decision, source="mock")
        return decision

    def _log_decision(self, decision: dict, source: str) -> None:
        decision["source"] = source
        if not (Config.PERSISTENCE_ENABLED and Config.SAVE_BEHAVIOR_LOG):
            return
        with SessionLocal() as session:
            session.add(BehaviorLog(
                robot_id=self.robot_id,
                behavior=decision["behavior"],
                reason=decision.get("reason", ""),
                source=source,
            ))
            session.commit()

    # ---------- Claude ----------

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        return self._client

    def _history(self, session, limit: int = 10) -> list[dict]:
        rows = (session.query(ConversationMessage)
                .filter_by(robot_id=self.robot_id)
                .order_by(ConversationMessage.id.desc())
                .limit(limit).all())
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    def _ask_claude(self, state: dict, available: list[str]) -> dict | None:
        client = self._get_client()
        user_message = json.dumps({
            "personality_state": state,
            "available_behaviors": available,
            "recent_interactions": self._recent_interactions(),
        })

        with SessionLocal() as session:
            messages = self._history(session)
        messages.append({"role": "user", "content": user_message})

        # Server-side fallback: if a safety classifier declines, the request is
        # re-served by Anthropic's recommended fallback model in the same call.
        response = client.beta.messages.create(
            model=Config.CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

        if response.stop_reason == "refusal":
            logger.warning("Claude declined the request (refusal); using mock decision")
            return None

        text = next((b.text for b in response.content if b.type == "text"), "")
        decision = self._parse_decision(text, available)
        if decision and Config.PERSISTENCE_ENABLED and Config.SAVE_CONVERSATION_HISTORY:
            with SessionLocal() as session:
                session.add(ConversationMessage(robot_id=self.robot_id, role="user",
                                                content=user_message))
                session.add(ConversationMessage(robot_id=self.robot_id, role="assistant",
                                                content=text))
                session.commit()
        return decision

    def _recent_interactions(self, limit: int = 5) -> list[str]:
        with SessionLocal() as session:
            rows = (session.query(Interaction)
                    .filter_by(robot_id=self.robot_id)
                    .order_by(Interaction.id.desc())
                    .limit(limit).all())
            return [r.interaction_type for r in rows]

    @staticmethod
    def _parse_decision(text: str, available: list[str]) -> dict | None:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        behavior = data.get("behavior")
        if behavior not in available:
            return None
        return {"behavior": behavior, "reason": str(data.get("reason", ""))}

    # ---------- mock ----------

    def _mock_decision(self, state: dict, available: list[str]) -> dict:
        """Weighted decision that loosely mirrors what Claude would choose."""
        weights = {}
        for behavior in available:
            weight = 1.0
            if state["energy"] < 25:
                weight *= 5.0 if behavior in ("rest", "sit", "stretch") else 0.3
            if state["boredom"] > 60:
                weight *= 3.0 if behavior in ("walk_forward", "curious_sniff",
                                              "excited_jump", "spin_right") else 0.7
            if state["happiness"] > 70 and behavior in ("excited_jump", "wave_arm"):
                weight *= 2.0
            if state["curiosity"] > 70 and behavior == "curious_sniff":
                weight *= 3.0
            weights[behavior] = weight
        choice = random.choices(list(weights), weights=list(weights.values()))[0]
        reasons = {
            "rest": "My battery paws need a nap...",
            "walk_forward": "Adventure awaits, onward!",
            "curious_sniff": "What's that smell? Must investigate!",
            "excited_jump": "I just can't contain the zoomies!",
            "wave_arm": "Hi hi hi! Look at me!",
            "spin_right": "Chasing my tail counts as cardio.",
            "play_dead": "Dramatic flop for maximum attention.",
            "stretch": "Mmm, a big stretch after all that lounging.",
            "sit": "Being a good dog, as always.",
        }
        return {"behavior": choice,
                "reason": reasons.get(choice, "Felt like the right thing to do.")}

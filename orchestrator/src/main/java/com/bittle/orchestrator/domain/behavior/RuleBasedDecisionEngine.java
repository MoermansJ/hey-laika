package com.bittle.orchestrator.domain.behavior;

import com.bittle.orchestrator.domain.behavior.BehaviorDecision.DecisionSource;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

public class RuleBasedDecisionEngine implements DecisionEngine {

    private static final List<Action> PLAY = List.of(Action.PLAY_BOW, Action.SPIN, Action.BACKFLIP);

    private static final double LINGER = 0.3;

    private final boolean idleCycleEnabled;

    public RuleBasedDecisionEngine(boolean idleCycleEnabled) {
        this.idleCycleEnabled = idleCycleEnabled;
    }

    @Override
    public Decision decide(PersonalityState state) {
        if (state.posture() == Posture.SLEEPING) {
            return state.energy() >= 0.55
                    ? decision(state, Action.WAKE_UP, "rested enough, waking up")
                    : Decision.rest("sleeping, recovering energy");
        }

        if (state.energy() < 0.15) {
            return toward(state, Action.SLEEP, "exhausted, heading to sleep");
        }

        if (state.hunger() > 0.8 && lonelyFor(state, Duration.ofSeconds(30))) {
            return toward(state, Action.SEEK_ATTENTION, "craving attention");
        }

        if (state.boredom() > 0.7 && state.energy() > 0.5) {
            return toward(state, pick(state, PLAY, Action.PLAY_BOW), "bored and energetic, playing");
        }

        if (state.energy() < 0.35) {
            if (state.posture() == Posture.STANDING) {
                return decision(state, Action.SIT_DOWN, "low energy, sitting down to rest");
            }
            return decision(state, Action.IDLE_CALM, "low energy, resting");
        }

        if (idleCycleEnabled) {
            return idleCycle(state);
        }
        return decision(state, Action.IDLE_CALM, "content, idling");
    }

    private Decision idleCycle(PersonalityState state) {
        var last = state.lastAction();
        var linger = ThreadLocalRandom.current().nextDouble() < LINGER;
        return switch (state.posture()) {
            case SITTING -> {
                if (last == Action.SIT_DOWN && linger) {
                    yield decision(state, Action.IDLE_CALM, "idle cycle: settling into the sit");
                }
                if (last == Action.SIT_DOWN || last == Action.IDLE_CALM || last == null) {
                    yield decision(state, Action.LOOK_AROUND_LOW,
                            "idle cycle: sitting, looking around");
                }
                if (last == Action.LOOK_AROUND_LOW && linger) {
                    yield decision(state, Action.LOOK_AROUND_LOW,
                            "idle cycle: another look around");
                }
                yield decision(state, Action.STAND_UP, "idle cycle: getting up");
            }
            case STANDING -> {
                if (last == Action.STAND_UP) {
                    yield decision(state, Action.IDLE_CALM, "idle cycle: standing a moment");
                }
                if (last == Action.IDLE_CALM && linger) {
                    yield decision(state, Action.IDLE_CALM, "idle cycle: standing a while longer");
                }
                if (last == Action.IDLE_CALM
                        || (last == Action.LOOK_AROUND_SLOW && linger)) {
                    yield decision(state, Action.LOOK_AROUND_SLOW,
                            "idle cycle: standing, slow look around");
                }
                yield decision(state, Action.SIT_DOWN, "idle cycle: sitting back down");
            }
            case LYING, SLEEPING -> decision(state, Action.STAND_UP,
                    "idle cycle: rested, getting up");
        };
    }

    private Decision toward(PersonalityState state, Action target, String reasoning) {
        if (target.validFor(state.posture(), state.energy())) {
            return decision(state, target, reasoning);
        }
        Action step = switch (state.posture()) {
            case LYING, SLEEPING -> Action.STAND_UP;
            case STANDING, SITTING -> target == Action.SLEEP ? Action.LIE_DOWN : Action.STAND_UP;
        };
        if (step.validFor(state.posture(), state.energy())) {
            return decision(state, step, reasoning + " (via " + step.actionId() + ")");
        }
        return decision(state, Action.IDLE_CALM, reasoning + " (blocked, idling)");
    }

    private Action pick(PersonalityState state, List<Action> candidates, Action fallback) {
        var valid = candidates.stream()
                .filter(a -> a.validFor(state.posture(), state.energy()))
                .toList();
        if (valid.isEmpty()) {
            return fallback;
        }
        return valid.get(ThreadLocalRandom.current().nextInt(valid.size()));
    }

    private static boolean lonelyFor(PersonalityState state, Duration threshold) {
        return state.lastInteractionAt() == null
                || Duration.between(state.lastInteractionAt(), Instant.now())
                        .compareTo(threshold) > 0;
    }

    private static Decision decision(PersonalityState state, Action action, String reasoning) {
        if (!action.validFor(state.posture(), state.energy())) {
            return Decision.rest(reasoning + " (no valid action)");
        }
        return new Decision(action, reasoning, DecisionSource.RULE);
    }
}

package com.bittle.orchestrator.domain.behavior;

/**
 * Picks the next action from the posture- and safety-valid set. Phase 1 ships
 * the rule-based implementation; Phase 2 adds the Claude director which biases
 * (not replaces) the rule loop.
 */
public interface DecisionEngine {

    /**
     * @return the decision for this cycle; {@link Decision#action()} is null
     *         when the robot should do nothing this cycle (e.g. stay asleep).
     */
    Decision decide(PersonalityState state);

    record Decision(Action action, String reasoning, BehaviorDecision.DecisionSource source) {

        public static Decision rest(String reasoning) {
            return new Decision(null, reasoning, BehaviorDecision.DecisionSource.RULE);
        }
    }
}

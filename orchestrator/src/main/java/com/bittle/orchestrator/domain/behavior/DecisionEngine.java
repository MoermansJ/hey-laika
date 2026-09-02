package com.bittle.orchestrator.domain.behavior;

public interface DecisionEngine {

    Decision decide(PersonalityState state);

    record Decision(Action action, String reasoning, BehaviorDecision.DecisionSource source) {

        public static Decision rest(String reasoning) {
            return new Decision(null, reasoning, BehaviorDecision.DecisionSource.RULE);
        }
    }
}

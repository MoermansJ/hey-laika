package com.bittle.orchestrator.domain.behavior;

import java.time.Instant;
import java.util.List;

public record BehaviorDecision(String robotId, Instant decidedAt,
                               PersonalityState.Snapshot stateAtDecision,
                               List<String> validActions, String selectedAction,
                               DecisionSource source, String reasoning,
                               Boolean success, Long actualDurationMs) {

    public enum DecisionSource { RULE, CLAUDE, MANUAL }
}

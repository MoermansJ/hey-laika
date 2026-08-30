package com.bittle.orchestrator.behavior;

import java.time.Instant;
import java.util.List;

/** Audit-trail entry for one decision/action cycle of the behavior loop. */
public record BehaviorDecision(String robotId, Instant decidedAt,
                               PersonalityState.Snapshot stateAtDecision,
                               List<String> validActions, String selectedAction,
                               DecisionSource source, String reasoning,
                               Boolean success, Long actualDurationMs) {

    public enum DecisionSource { RULE, CLAUDE, MANUAL }
}

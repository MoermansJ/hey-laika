package com.bittle.orchestrator.domain.behavior;

import java.time.Instant;
import java.util.Objects;

/**
 * Result of judging whether an agent run achieved its declared goal
 * (AGENT_TOOL_COMPOSITION_DESIGN.md §2.1). Attached to a {@link BehaviorRunLog}
 * after execution; absent (null) on non-agent runs.
 *
 * @param success          true / false, or null when the evaluator could not decide
 * @param confidence       0.0-1.0, or null when not reported
 * @param reason           human-readable explanation
 * @param evaluatorVersion version of the evaluator that produced this result
 * @param evaluatedAt      when the evaluation happened; required, it marks the outcome as present
 */
public record OutcomeEvaluation(Boolean success, Double confidence, String reason,
                                String evaluatorVersion, Instant evaluatedAt) {

    public OutcomeEvaluation {
        Objects.requireNonNull(evaluatedAt, "evaluatedAt");
        if (confidence != null && (confidence.isNaN() || confidence < 0.0 || confidence > 1.0)) {
            throw new IllegalArgumentException("confidence must be within 0.0-1.0: " + confidence);
        }
    }
}

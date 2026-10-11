package com.bittle.orchestrator.domain.behavior.outcome;

/**
 * What a {@link GoalOutcomeChecker} concluded, before the evaluator stamps
 * version and time onto it as an {@code OutcomeEvaluation}.
 *
 * @param success    true / false, or null when the data did not allow a verdict
 * @param confidence 0.0-1.0; values outside the range are clamped and NaN becomes 0.0
 * @param reason     human-readable explanation (never null)
 */
public record GoalCheck(Boolean success, double confidence, String reason) {

    public GoalCheck {
        confidence = Double.isNaN(confidence) ? 0.0 : Math.max(0.0, Math.min(1.0, confidence));
        reason = reason == null ? "" : reason;
    }

    public static GoalCheck succeeded(double confidence, String reason) {
        return new GoalCheck(true, confidence, reason);
    }

    public static GoalCheck failed(double confidence, String reason) {
        return new GoalCheck(false, confidence, reason);
    }

    /** No verdict: the checker lacked the data it needs. */
    public static GoalCheck undetermined(String reason) {
        return new GoalCheck(null, 0.0, reason);
    }
}

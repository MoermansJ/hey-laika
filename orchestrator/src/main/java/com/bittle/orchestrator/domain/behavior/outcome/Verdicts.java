package com.bittle.orchestrator.domain.behavior.outcome;

/** Shared threshold-to-verdict rule for the goal outcome checkers. */
final class Verdicts {

    private Verdicts() {
    }

    /**
     * Success when {@code change >= threshold}. A success's confidence grows with
     * the change up to {@code scale}; a failure's confidence is high when nothing
     * changed and falls toward 0 as the change approaches the threshold.
     */
    static GoalCheck judge(double change, double threshold, double scale, String reason) {
        if (change >= threshold) {
            return GoalCheck.succeeded(Math.min(1.0, change / scale), reason);
        }
        double progress = Math.max(0.0, change) / threshold;
        return GoalCheck.failed(1.0 - Math.min(1.0, progress), reason);
    }

    /** Signed smallest angle from {@code fromDeg} to {@code toDeg}, in (-180, 180]. */
    static double angleDelta(double fromDeg, double toDeg) {
        double delta = (toDeg - fromDeg) % 360.0;
        if (delta > 180.0) {
            delta -= 360.0;
        } else if (delta <= -180.0) {
            delta += 360.0;
        }
        return delta;
    }
}

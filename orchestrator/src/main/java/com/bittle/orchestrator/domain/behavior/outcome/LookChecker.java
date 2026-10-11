package com.bittle.orchestrator.domain.behavior.outcome;

import java.util.Locale;
import java.util.Objects;

/**
 * Base for the look_* goals. Primary signal: the camera motion centroid moved in
 * the looked-at direction (AGENT_TOOL_COMPOSITION_DESIGN.md §3.2: for look_upward,
 * "centroid moved upward (y decreased)"). When either snapshot lacks a centroid,
 * the head IMU is used instead (pitch for up, yaw for left/right).
 */
public abstract class LookChecker implements GoalOutcomeChecker {

    private final OutcomeThresholds thresholds;

    protected LookChecker(OutcomeThresholds thresholds) {
        this.thresholds = Objects.requireNonNull(thresholds, "thresholds");
    }

    /** Centroid shift in the looked-at direction, pixels (positive = toward it). */
    protected abstract double centroidShift(SensorSnapshot.Point before,
                                            SensorSnapshot.Point after);

    /** Head rotation toward the looked-at direction, degrees (positive = toward it). */
    protected abstract double imuTurn(SensorSnapshot.Imu before, SensorSnapshot.Imu after);

    /** Word for the direction in reasons: "upward", "left", "right". */
    protected abstract String direction();

    @Override
    public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
        if (before.motionCentroid() != null && after.motionCentroid() != null) {
            double shift = centroidShift(before.motionCentroid(), after.motionCentroid());
            return Verdicts.judge(shift, thresholds.lookCentroidPx(),
                    thresholds.lookCentroidScalePx(), String.format(Locale.ROOT,
                            "Motion centroid moved %.0f px %s (threshold: %.0f px)",
                            Math.abs(shift), shift >= 0 ? direction() : "the other way",
                            thresholds.lookCentroidPx()));
        }
        if (before.headImu() != null && after.headImu() != null) {
            double turn = imuTurn(before.headImu(), after.headImu());
            return Verdicts.judge(turn, thresholds.lookImuDeg(), thresholds.lookImuScaleDeg(),
                    String.format(Locale.ROOT,
                            "Head turned %.1f deg %s by IMU (threshold: %.1f deg)",
                            Math.abs(turn), turn >= 0 ? direction() : "the other way",
                            thresholds.lookImuDeg()));
        }
        return GoalCheck.undetermined("Insufficient camera and IMU data to judge looking "
                + direction());
    }
}

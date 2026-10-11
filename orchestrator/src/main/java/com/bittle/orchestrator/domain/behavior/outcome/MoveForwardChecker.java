package com.bittle.orchestrator.domain.behavior.outcome;

import java.util.Locale;
import java.util.Objects;

/**
 * move_forward: odometry distance travelled along the heading the robot had
 * before the run (so sideways drift and backing up do not count).
 */
public class MoveForwardChecker implements GoalOutcomeChecker {

    public static final String GOAL = "move_forward";

    private final OutcomeThresholds thresholds;

    public MoveForwardChecker(OutcomeThresholds thresholds) {
        this.thresholds = Objects.requireNonNull(thresholds, "thresholds");
    }

    @Override
    public String goal() {
        return GOAL;
    }

    @Override
    public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
        var from = before.odometryPosition();
        var to = after.odometryPosition();
        if (from == null || to == null) {
            return GoalCheck.undetermined("Insufficient odometry data");
        }
        double heading = Math.toRadians(from.headingDeg());
        double forward = (to.xCm() - from.xCm()) * Math.cos(heading)
                + (to.yCm() - from.yCm()) * Math.sin(heading);
        return Verdicts.judge(forward, thresholds.moveForwardCm(),
                thresholds.moveForwardScaleCm(), String.format(Locale.ROOT,
                        "Moved forward %.1f cm (threshold: %.1f cm)", forward,
                        thresholds.moveForwardCm()));
    }
}

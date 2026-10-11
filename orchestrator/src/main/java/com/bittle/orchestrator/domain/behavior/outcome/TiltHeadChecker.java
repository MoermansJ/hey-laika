package com.bittle.orchestrator.domain.behavior.outcome;

import java.util.Locale;
import java.util.Objects;

/** tilt_head: the head IMU roll changed, to either side. */
public class TiltHeadChecker implements GoalOutcomeChecker {

    public static final String GOAL = "tilt_head";

    private final OutcomeThresholds thresholds;

    public TiltHeadChecker(OutcomeThresholds thresholds) {
        this.thresholds = Objects.requireNonNull(thresholds, "thresholds");
    }

    @Override
    public String goal() {
        return GOAL;
    }

    @Override
    public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
        if (before.headImu() == null || after.headImu() == null) {
            return GoalCheck.undetermined("Insufficient IMU data");
        }
        double roll = Verdicts.angleDelta(before.headImu().rollDeg(), after.headImu().rollDeg());
        return Verdicts.judge(Math.abs(roll), thresholds.tiltHeadDeg(),
                thresholds.tiltHeadScaleDeg(), String.format(Locale.ROOT,
                        "Head rolled %.1f deg %s (threshold: %.1f deg)", Math.abs(roll),
                        roll >= 0 ? "right" : "left", thresholds.tiltHeadDeg()));
    }
}

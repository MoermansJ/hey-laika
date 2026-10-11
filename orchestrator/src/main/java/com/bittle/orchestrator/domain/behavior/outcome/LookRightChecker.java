package com.bittle.orchestrator.domain.behavior.outcome;

/** look_right: centroid x increased, or head yaw turned right (clockwise). */
public class LookRightChecker extends LookChecker {

    public static final String GOAL = "look_right";

    public LookRightChecker(OutcomeThresholds thresholds) {
        super(thresholds);
    }

    @Override
    public String goal() {
        return GOAL;
    }

    @Override
    protected double centroidShift(SensorSnapshot.Point before, SensorSnapshot.Point after) {
        return after.x() - before.x();
    }

    @Override
    protected double imuTurn(SensorSnapshot.Imu before, SensorSnapshot.Imu after) {
        return -Verdicts.angleDelta(before.yawDeg(), after.yawDeg());
    }

    @Override
    protected String direction() {
        return "right";
    }
}

package com.bittle.orchestrator.domain.behavior.outcome;

/** look_left: centroid x decreased, or head yaw turned left (counter-clockwise). */
public class LookLeftChecker extends LookChecker {

    public static final String GOAL = "look_left";

    public LookLeftChecker(OutcomeThresholds thresholds) {
        super(thresholds);
    }

    @Override
    public String goal() {
        return GOAL;
    }

    @Override
    protected double centroidShift(SensorSnapshot.Point before, SensorSnapshot.Point after) {
        return before.x() - after.x();
    }

    @Override
    protected double imuTurn(SensorSnapshot.Imu before, SensorSnapshot.Imu after) {
        return Verdicts.angleDelta(before.yawDeg(), after.yawDeg());
    }

    @Override
    protected String direction() {
        return "left";
    }
}

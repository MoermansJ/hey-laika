package com.bittle.orchestrator.domain.behavior.outcome;

/** look_upward: centroid y decreased, or head pitch rose. */
public class LookUpwardChecker extends LookChecker {

    public static final String GOAL = "look_upward";

    public LookUpwardChecker(OutcomeThresholds thresholds) {
        super(thresholds);
    }

    @Override
    public String goal() {
        return GOAL;
    }

    @Override
    protected double centroidShift(SensorSnapshot.Point before, SensorSnapshot.Point after) {
        return before.y() - after.y();
    }

    @Override
    protected double imuTurn(SensorSnapshot.Imu before, SensorSnapshot.Imu after) {
        return after.pitchDeg() - before.pitchDeg();
    }

    @Override
    protected String direction() {
        return "upward";
    }
}

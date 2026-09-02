package com.bittle.orchestrator.domain.robot;

/**
 * Live status as reported by the robot's adapter. Field names mirror the
 * adapter's camelCase JSON exactly, as do all records in this package.
 */
public record RobotStatus(String robotId, boolean connected, String mode,
                          String lastCommand, Integer commandsSent,
                          Boolean autonomous, String mood, Double battery,
                          String signal, Long uptimeSeconds,
                          Double startedAt) {

    public static RobotStatus unreachable(String robotId) {
        return new RobotStatus(robotId, false, null, null, null, null, null,
                null, null, null, null);
    }
}

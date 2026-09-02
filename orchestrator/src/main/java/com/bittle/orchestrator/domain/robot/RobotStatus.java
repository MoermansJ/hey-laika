package com.bittle.orchestrator.domain.robot;

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

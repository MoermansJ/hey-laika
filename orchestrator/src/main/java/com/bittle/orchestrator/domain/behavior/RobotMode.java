package com.bittle.orchestrator.domain.behavior;

import java.time.Instant;

public record RobotMode(String robotId, OperatingMode mode, Instant changedAt, String changedBy) {

    public static RobotMode initial(String robotId) {
        return new RobotMode(robotId, OperatingMode.STATIONARY, Instant.now(), "default");
    }
}

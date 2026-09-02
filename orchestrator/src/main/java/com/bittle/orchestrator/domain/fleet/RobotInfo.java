package com.bittle.orchestrator.domain.fleet;

public record RobotInfo(String robotId, String name, String type, String serviceUrl,
                        boolean active) {
}

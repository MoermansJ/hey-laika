package com.bittle.orchestrator.domain.fleet;

/** Robot listing entry served to the dashboard. */
public record RobotInfo(String robotId, String name, String type, String serviceUrl,
                        boolean active) {
}

package com.bittle.orchestrator.domain.fleet;

public record Robot(String id, String name, String type, String serviceUrl) {

    public RobotInfo info() {
        return new RobotInfo(id, name, type, serviceUrl, true);
    }
}

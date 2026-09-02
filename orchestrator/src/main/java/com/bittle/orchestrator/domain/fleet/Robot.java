package com.bittle.orchestrator.domain.fleet;

/**
 * Identity of one managed robot and where its Python adapter service lives.
 * All hardware/AI concerns are delegated to that adapter.
 */
public record Robot(String id, String name, String type, String serviceUrl) {

    public RobotInfo info() {
        return new RobotInfo(id, name, type, serviceUrl, true);
    }
}

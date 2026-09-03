package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.BinaryContent;

public class RelayGetBinaryFromRobotUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public RelayGetBinaryFromRobotUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public BinaryContent execute(String robotId, String path) {
        return adapter.getBinary(registry.get(robotId), path);
    }
}

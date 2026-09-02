package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.RobotStatus;

public class GetRobotStatusUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetRobotStatusUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public RobotStatus execute(String robotId) {
        return adapter.status(registry.get(robotId));
    }
}

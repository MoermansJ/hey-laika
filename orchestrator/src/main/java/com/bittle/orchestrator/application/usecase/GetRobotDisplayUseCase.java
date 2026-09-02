package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.DisplayContent;

public class GetRobotDisplayUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetRobotDisplayUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public DisplayContent execute(String robotId) {
        return adapter.display(registry.get(robotId));
    }
}

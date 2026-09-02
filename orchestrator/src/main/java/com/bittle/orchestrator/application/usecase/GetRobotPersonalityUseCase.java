package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.RobotPersonality;

public class GetRobotPersonalityUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetRobotPersonalityUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public RobotPersonality execute(String robotId) {
        return adapter.personality(registry.get(robotId));
    }
}

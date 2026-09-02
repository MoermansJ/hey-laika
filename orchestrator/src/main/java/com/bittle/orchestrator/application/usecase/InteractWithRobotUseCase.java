package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.InteractionResult;

public class InteractWithRobotUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public InteractWithRobotUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public InteractionResult execute(String robotId, String type) {
        return adapter.interact(registry.get(robotId), type);
    }
}

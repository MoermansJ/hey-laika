package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.RobotBehavior;

public class GetNextBehaviorUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetNextBehaviorUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public RobotBehavior execute(String robotId) {
        return adapter.nextBehavior(registry.get(robotId));
    }
}

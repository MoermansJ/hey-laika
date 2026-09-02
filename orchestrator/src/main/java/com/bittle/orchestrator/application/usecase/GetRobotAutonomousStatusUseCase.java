package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.AutonomousState;

public class GetRobotAutonomousStatusUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetRobotAutonomousStatusUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public AutonomousState execute(String robotId) {
        return adapter.autonomousStatus(registry.get(robotId));
    }
}

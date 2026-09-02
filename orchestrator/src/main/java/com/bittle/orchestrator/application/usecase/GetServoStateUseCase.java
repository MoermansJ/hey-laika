package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.ServoState;

public class GetServoStateUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetServoStateUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public ServoState execute(String robotId) {
        return adapter.servoState(registry.get(robotId));
    }
}

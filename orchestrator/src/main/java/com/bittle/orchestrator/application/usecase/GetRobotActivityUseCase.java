package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.ActivityLog;

public class GetRobotActivityUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetRobotActivityUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public ActivityLog execute(String robotId) {
        return adapter.activity(registry.get(robotId));
    }
}

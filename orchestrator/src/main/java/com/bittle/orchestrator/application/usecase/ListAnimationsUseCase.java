package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.AnimationList;

public class ListAnimationsUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public ListAnimationsUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public AnimationList execute(String robotId) {
        return adapter.animations(registry.get(robotId));
    }
}

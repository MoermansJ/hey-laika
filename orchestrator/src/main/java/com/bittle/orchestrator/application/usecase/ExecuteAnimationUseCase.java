package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.AnimationResult;

public class ExecuteAnimationUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public ExecuteAnimationUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public AnimationResult execute(String robotId, String animation) {
        return adapter.executeAnimation(registry.get(robotId), animation);
    }
}

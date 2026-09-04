package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.AnimationResult;

public class ExecuteAnimationUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public ExecuteAnimationUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public AnimationResult execute(String robotId, String animation) {
        return adapter.executeAnimation(fleet.get(robotId), animation);
    }
}

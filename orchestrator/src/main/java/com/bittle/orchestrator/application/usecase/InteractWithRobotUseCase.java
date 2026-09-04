package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.InteractionResult;

public class InteractWithRobotUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public InteractWithRobotUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public InteractionResult execute(String robotId, String type) {
        return adapter.interact(fleet.get(robotId), type);
    }
}

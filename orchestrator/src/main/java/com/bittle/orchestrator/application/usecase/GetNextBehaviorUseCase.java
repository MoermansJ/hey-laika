package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.RobotBehavior;

public class GetNextBehaviorUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetNextBehaviorUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public RobotBehavior execute(String robotId) {
        return adapter.nextBehavior(fleet.get(robotId));
    }
}

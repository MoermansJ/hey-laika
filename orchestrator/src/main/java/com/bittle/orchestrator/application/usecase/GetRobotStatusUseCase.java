package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.RobotStatus;

public class GetRobotStatusUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetRobotStatusUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public RobotStatus execute(String robotId) {
        return adapter.status(fleet.get(robotId));
    }
}

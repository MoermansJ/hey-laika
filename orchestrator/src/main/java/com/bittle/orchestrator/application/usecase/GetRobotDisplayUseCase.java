package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.DisplayContent;

public class GetRobotDisplayUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetRobotDisplayUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public DisplayContent execute(String robotId) {
        return adapter.display(fleet.get(robotId));
    }
}

package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.ActivityLog;

public class GetRobotActivityUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetRobotActivityUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public ActivityLog execute(String robotId) {
        return adapter.activity(fleet.get(robotId));
    }
}

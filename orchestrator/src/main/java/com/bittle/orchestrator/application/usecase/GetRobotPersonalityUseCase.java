package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.RobotPersonality;

public class GetRobotPersonalityUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetRobotPersonalityUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public RobotPersonality execute(String robotId) {
        return adapter.personality(fleet.get(robotId));
    }
}

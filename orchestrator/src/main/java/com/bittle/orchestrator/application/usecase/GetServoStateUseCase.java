package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.ServoState;

public class GetServoStateUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetServoStateUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public ServoState execute(String robotId) {
        return adapter.servoState(fleet.get(robotId));
    }
}

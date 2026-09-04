package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.AutonomousState;

public class GetRobotAutonomousStatusUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetRobotAutonomousStatusUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public AutonomousState execute(String robotId) {
        return adapter.autonomousStatus(fleet.get(robotId));
    }
}

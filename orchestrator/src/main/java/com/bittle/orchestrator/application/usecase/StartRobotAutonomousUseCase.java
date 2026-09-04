package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.AutonomousState;

public class StartRobotAutonomousUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public StartRobotAutonomousUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public AutonomousState execute(String robotId) {
        return adapter.startAutonomous(fleet.get(robotId));
    }
}

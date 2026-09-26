package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import com.bittle.orchestrator.domain.fleet.Fleet;

public class GetRobotModeUseCase {

    private final Fleet fleet;
    private final RobotModeRepositoryPort modes;

    public GetRobotModeUseCase(Fleet fleet, RobotModeRepositoryPort modes) {
        this.fleet = fleet;
        this.modes = modes;
    }

    public RobotMode execute(String robotId) {
        fleet.get(robotId);
        return modes.find(robotId).orElseGet(() -> RobotMode.initial(robotId));
    }
}

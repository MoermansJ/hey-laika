package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotInfo;
import java.util.List;

public class ListRobotsUseCase {

    private final Fleet fleet;

    public ListRobotsUseCase(Fleet fleet) {
        this.fleet = fleet;
    }

    public List<RobotInfo> execute() {
        return fleet.all().stream().map(Robot::info).toList();
    }
}

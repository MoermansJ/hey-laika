package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotInfo;
import java.util.List;

public class ListRobotsUseCase {

    private final FleetRegistry registry;

    public ListRobotsUseCase(FleetRegistry registry) {
        this.registry = registry;
    }

    public List<RobotInfo> execute() {
        return registry.all().stream().map(Robot::info).toList();
    }
}

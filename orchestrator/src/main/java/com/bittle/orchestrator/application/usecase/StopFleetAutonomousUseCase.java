package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetSweep;
import java.util.Map;

public class StopFleetAutonomousUseCase {

    private final FleetSweep sweep;
    private final RobotAdapterPort adapter;

    public StopFleetAutonomousUseCase(FleetSweep sweep, RobotAdapterPort adapter) {
        this.sweep = sweep;
        this.adapter = adapter;
    }

    public Map<String, Boolean> execute() {
        return sweep.forAll(robot -> !adapter.stopAutonomous(robot).running());
    }
}

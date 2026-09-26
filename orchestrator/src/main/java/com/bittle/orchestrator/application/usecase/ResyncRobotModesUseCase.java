package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ResyncRobotModesUseCase {

    private static final Logger log = LoggerFactory.getLogger(ResyncRobotModesUseCase.class);

    private final Fleet fleet;
    private final RobotModeRepositoryPort modes;
    private final RobotAdapterPort adapter;

    public ResyncRobotModesUseCase(Fleet fleet, RobotModeRepositoryPort modes,
                                   RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.modes = modes;
        this.adapter = adapter;
    }

    public void execute() {
        fleet.all().forEach(this::resync);
    }

    private void resync(Robot robot) {
        var mode = modes.find(robot.id()).map(RobotMode::mode).orElse(OperatingMode.STATIONARY);
        try {
            adapter.post(robot, "/mode", Map.of("mode", mode.wireId()));
        } catch (RuntimeException e) {
            log.debug("Skipping mode resync for {}: {}", robot.id(), e.getMessage());
        }
    }
}

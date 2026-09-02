package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.port.in.FleetUseCase;
import com.bittle.orchestrator.domain.fleet.FleetStats;
import com.bittle.orchestrator.domain.fleet.RobotInfo;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/fleet")
public class FleetController {

    private final FleetUseCase fleet;

    public FleetController(FleetUseCase fleet) {
        this.fleet = fleet;
    }

    @GetMapping("/robots")
    public List<RobotInfo> robots() {
        return fleet.robots();
    }

    @GetMapping("/status")
    public Map<String, RobotStatus> status() {
        return fleet.fleetStatus();
    }

    @GetMapping("/stats")
    public FleetStats stats() {
        return fleet.stats();
    }

    @PostMapping("/autonomous/start")
    public Map<String, Boolean> startAllAutonomous() {
        return fleet.startAllAutonomous();
    }

    @PostMapping("/autonomous/stop")
    public Map<String, Boolean> stopAllAutonomous() {
        return fleet.stopAllAutonomous();
    }
}

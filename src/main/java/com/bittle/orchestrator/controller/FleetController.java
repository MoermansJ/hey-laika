package com.bittle.orchestrator.controller;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.dto.Dtos.FleetStats;
import com.bittle.orchestrator.dto.Dtos.RobotInfo;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.fleet.FleetManager;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/fleet")
public class FleetController {

    private final FleetManager fleetManager;

    public FleetController(FleetManager fleetManager) {
        this.fleetManager = fleetManager;
    }

    @GetMapping("/robots")
    public List<RobotInfo> robots() {
        return fleetManager.all().stream().map(RobotAgent::info).toList();
    }

    @GetMapping("/status")
    public Map<String, RobotStatus> status() {
        return fleetManager.fleetStatus();
    }

    @GetMapping("/stats")
    public FleetStats stats() {
        return fleetManager.stats();
    }

    @PostMapping("/autonomous/start")
    public Map<String, Boolean> startAllAutonomous() {
        return fleetManager.forAll(agent -> agent.startAutonomous().running());
    }

    @PostMapping("/autonomous/stop")
    public Map<String, Boolean> stopAllAutonomous() {
        return fleetManager.forAll(agent -> !agent.stopAutonomous().running());
    }
}

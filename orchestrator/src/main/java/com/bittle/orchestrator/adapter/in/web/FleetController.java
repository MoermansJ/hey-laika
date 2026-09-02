package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetFleetStatsUseCase;
import com.bittle.orchestrator.application.usecase.GetFleetStatusUseCase;
import com.bittle.orchestrator.application.usecase.ListRobotsUseCase;
import com.bittle.orchestrator.application.usecase.StartFleetAutonomousUseCase;
import com.bittle.orchestrator.application.usecase.StopFleetAutonomousUseCase;
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

    private final ListRobotsUseCase listRobots;
    private final GetFleetStatusUseCase getStatus;
    private final GetFleetStatsUseCase getStats;
    private final StartFleetAutonomousUseCase startAutonomous;
    private final StopFleetAutonomousUseCase stopAutonomous;

    public FleetController(ListRobotsUseCase listRobots, GetFleetStatusUseCase getStatus,
                           GetFleetStatsUseCase getStats,
                           StartFleetAutonomousUseCase startAutonomous,
                           StopFleetAutonomousUseCase stopAutonomous) {
        this.listRobots = listRobots;
        this.getStatus = getStatus;
        this.getStats = getStats;
        this.startAutonomous = startAutonomous;
        this.stopAutonomous = stopAutonomous;
    }

    @GetMapping("/robots")
    public List<RobotInfo> robots() {
        return listRobots.execute();
    }

    @GetMapping("/status")
    public Map<String, RobotStatus> status() {
        return getStatus.execute();
    }

    @GetMapping("/stats")
    public FleetStats stats() {
        return getStats.execute();
    }

    @PostMapping("/autonomous/start")
    public Map<String, Boolean> startAllAutonomous() {
        return startAutonomous.execute();
    }

    @PostMapping("/autonomous/stop")
    public Map<String, Boolean> stopAllAutonomous() {
        return stopAutonomous.execute();
    }
}

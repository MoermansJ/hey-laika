package com.bittle.orchestrator.controller;

import com.bittle.orchestrator.dto.Dtos.ActivityLog;
import com.bittle.orchestrator.dto.Dtos.AnimationList;
import com.bittle.orchestrator.dto.Dtos.AnimationResult;
import com.bittle.orchestrator.dto.Dtos.AutonomousState;
import com.bittle.orchestrator.dto.Dtos.CommandRequest;
import com.bittle.orchestrator.dto.Dtos.CommandResult;
import com.bittle.orchestrator.dto.Dtos.DisplayContent;
import com.bittle.orchestrator.dto.Dtos.InteractionResult;
import com.bittle.orchestrator.dto.Dtos.RobotBehavior;
import com.bittle.orchestrator.dto.Dtos.RobotPersonality;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.fleet.FleetManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Proxies robot-scoped operations to the robot's Python adapter service. */
@RestController
@RequestMapping("/api/robots/{robotId}")
public class RobotController {

    private final FleetManager fleetManager;

    public RobotController(FleetManager fleetManager) {
        this.fleetManager = fleetManager;
    }

    @GetMapping("/status")
    public RobotStatus status(@PathVariable String robotId) {
        return fleetManager.get(robotId).status();
    }

    @GetMapping("/personality")
    public RobotPersonality personality(@PathVariable String robotId) {
        return fleetManager.get(robotId).personality();
    }

    @GetMapping("/behavior")
    public RobotBehavior behavior(@PathVariable String robotId) {
        return fleetManager.get(robotId).nextBehavior();
    }

    @PostMapping("/command")
    public CommandResult command(@PathVariable String robotId,
                                 @RequestBody CommandRequest request) {
        return fleetManager.get(robotId).command(request.command());
    }

    @PostMapping("/interact/{type}")
    public InteractionResult interact(@PathVariable String robotId, @PathVariable String type) {
        return fleetManager.get(robotId).interact(type);
    }

    @GetMapping("/choreography/list")
    public AnimationList animations(@PathVariable String robotId) {
        return fleetManager.get(robotId).animations();
    }

    @PostMapping("/choreography/execute/{animation}")
    public AnimationResult executeAnimation(@PathVariable String robotId,
                                            @PathVariable String animation) {
        return fleetManager.get(robotId).executeAnimation(animation);
    }

    @PostMapping("/autonomous/start")
    public AutonomousState startAutonomous(@PathVariable String robotId) {
        return fleetManager.get(robotId).startAutonomous();
    }

    @PostMapping("/autonomous/stop")
    public AutonomousState stopAutonomous(@PathVariable String robotId) {
        return fleetManager.get(robotId).stopAutonomous();
    }

    @GetMapping("/autonomous/status")
    public AutonomousState autonomousStatus(@PathVariable String robotId) {
        return fleetManager.get(robotId).autonomousStatus();
    }

    @GetMapping("/activity")
    public ActivityLog activity(@PathVariable String robotId) {
        return fleetManager.get(robotId).activity();
    }

    @GetMapping("/display")
    public DisplayContent display(@PathVariable String robotId) {
        return fleetManager.get(robotId).display();
    }
}

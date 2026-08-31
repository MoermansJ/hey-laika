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
import com.bittle.orchestrator.behavior.BehaviorService;
import com.bittle.orchestrator.dto.Dtos.ActionResult;
import com.bittle.orchestrator.dto.Dtos.ExecuteActionRequest;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.dto.Dtos.ServoMoveRequest;
import com.bittle.orchestrator.dto.Dtos.ServoMoveResult;
import com.bittle.orchestrator.dto.Dtos.ServoState;
import com.bittle.orchestrator.fleet.FleetManager;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
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
    private final BehaviorService behaviorService;

    public RobotController(FleetManager fleetManager, BehaviorService behaviorService) {
        this.fleetManager = fleetManager;
        this.behaviorService = behaviorService;
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

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities(@PathVariable String robotId) {
        return fleetManager.get(robotId).capabilities();
    }

    @GetMapping("/servo")
    public ServoState servoState(@PathVariable String robotId) {
        return fleetManager.get(robotId).servoState();
    }

    @PostMapping("/servo")
    public ServoMoveResult moveServos(@PathVariable String robotId,
                                      @RequestBody ServoMoveRequest request) {
        return fleetManager.get(robotId).moveServos(request);
    }

    @PostMapping("/voice/demo")
    public Map<String, Object> voiceDemo(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return fleetManager.get(robotId).voiceDemo(body);
    }

    @GetMapping("/voice/health")
    public Map<String, Object> voiceHealth(@PathVariable String robotId) {
        return fleetManager.get(robotId).voiceHealth();
    }

    @PostMapping("/sound")
    public Map<String, Object> sound(@PathVariable String robotId,
                                     @RequestBody Map<String, Object> body) {
        return fleetManager.get(robotId).sound(body);
    }

    /**
     * Direct movement execution for the choreography builder. Refused while
     * the behavior loop drives the robot — the two would race on the servos.
     */
    @PostMapping("/execute_action")
    public ResponseEntity<?> executeAction(@PathVariable String robotId,
                                           @RequestBody ExecuteActionRequest request) {
        if (behaviorService.loop(robotId).isRunning()) {
            return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of(
                    "error", "behavior_loop_running",
                    "message", "Stop the behavior loop before running a sequence."));
        }
        ActionResult result = fleetManager.get(robotId).executeAction(request);
        return ResponseEntity.ok(result);
    }
}

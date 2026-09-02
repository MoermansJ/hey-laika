package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.port.in.RobotOperationsUseCase;
import com.bittle.orchestrator.application.port.in.RobotPassthroughUseCase;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.ActivityLog;
import com.bittle.orchestrator.domain.robot.AnimationList;
import com.bittle.orchestrator.domain.robot.AnimationResult;
import com.bittle.orchestrator.domain.robot.AutonomousState;
import com.bittle.orchestrator.domain.robot.CommandRequest;
import com.bittle.orchestrator.domain.robot.CommandResult;
import com.bittle.orchestrator.domain.robot.DisplayContent;
import com.bittle.orchestrator.domain.robot.ExecuteActionRequest;
import com.bittle.orchestrator.domain.robot.InteractionResult;
import com.bittle.orchestrator.domain.robot.RobotBehavior;
import com.bittle.orchestrator.domain.robot.RobotPersonality;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import com.bittle.orchestrator.domain.robot.ServoMoveRequest;
import com.bittle.orchestrator.domain.robot.ServoMoveResult;
import com.bittle.orchestrator.domain.robot.ServoState;
import java.util.Map;
import java.util.Set;
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

    private static final Set<String> GREETING_ACTIONS = Set.of("run", "enable", "disable");
    private static final Set<String> IDLE_ACTIONS = Set.of("enable", "disable");

    private final RobotOperationsUseCase robots;
    private final RobotPassthroughUseCase passthrough;

    public RobotController(RobotOperationsUseCase robots, RobotPassthroughUseCase passthrough) {
        this.robots = robots;
        this.passthrough = passthrough;
    }

    @GetMapping("/status")
    public RobotStatus status(@PathVariable String robotId) {
        return robots.status(robotId);
    }

    @GetMapping("/personality")
    public RobotPersonality personality(@PathVariable String robotId) {
        return robots.personality(robotId);
    }

    @GetMapping("/behavior")
    public RobotBehavior behavior(@PathVariable String robotId) {
        return robots.nextBehavior(robotId);
    }

    @PostMapping("/command")
    public CommandResult command(@PathVariable String robotId,
                                 @RequestBody CommandRequest request) {
        return robots.command(robotId, request.command());
    }

    @PostMapping("/interact/{type}")
    public InteractionResult interact(@PathVariable String robotId, @PathVariable String type) {
        return robots.interact(robotId, type);
    }

    @GetMapping("/choreography/list")
    public AnimationList animations(@PathVariable String robotId) {
        return robots.animations(robotId);
    }

    @PostMapping("/choreography/execute/{animation}")
    public AnimationResult executeAnimation(@PathVariable String robotId,
                                            @PathVariable String animation) {
        return robots.executeAnimation(robotId, animation);
    }

    @PostMapping("/autonomous/start")
    public AutonomousState startAutonomous(@PathVariable String robotId) {
        return robots.startAutonomous(robotId);
    }

    @PostMapping("/autonomous/stop")
    public AutonomousState stopAutonomous(@PathVariable String robotId) {
        return robots.stopAutonomous(robotId);
    }

    @GetMapping("/autonomous/status")
    public AutonomousState autonomousStatus(@PathVariable String robotId) {
        return robots.autonomousStatus(robotId);
    }

    @GetMapping("/activity")
    public ActivityLog activity(@PathVariable String robotId) {
        return robots.activity(robotId);
    }

    @GetMapping("/display")
    public DisplayContent display(@PathVariable String robotId) {
        return robots.display(robotId);
    }

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities(@PathVariable String robotId) {
        return robots.capabilities(robotId);
    }

    @GetMapping("/servo")
    public ServoState servoState(@PathVariable String robotId) {
        return robots.servoState(robotId);
    }

    @PostMapping("/servo")
    public ServoMoveResult moveServos(@PathVariable String robotId,
                                      @RequestBody ServoMoveRequest request) {
        return robots.moveServos(robotId, request);
    }

    @PostMapping("/voice/demo")
    public Map<String, Object> voiceDemo(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return robots.voiceDemo(robotId, body);
    }

    @GetMapping("/voice/health")
    public Map<String, Object> voiceHealth(@PathVariable String robotId) {
        return robots.voiceHealth(robotId);
    }

    @PostMapping("/sound")
    public Map<String, Object> sound(@PathVariable String robotId,
                                     @RequestBody Map<String, Object> body) {
        return robots.sound(robotId, body);
    }

    /**
     * Direct movement execution for the choreography builder. Refused with 409
     * while the behavior loop drives the robot (see GlobalExceptionHandler).
     */
    @PostMapping("/execute_action")
    public ActionResult executeAction(@PathVariable String robotId,
                                      @RequestBody ExecuteActionRequest request) {
        return robots.executeAction(robotId, request);
    }

    // ---- Host-side lifecycle behaviors (greeting / idle) — whitelisted
    // passthrough to the adapter; the GUI reads and toggles them here. ----

    @GetMapping("/greeting")
    public Map<String, Object> greeting(@PathVariable String robotId) {
        return passthrough.get(robotId, "/greeting");
    }

    @PostMapping("/greeting/{action}")
    public ResponseEntity<?> greetingAction(@PathVariable String robotId,
                                            @PathVariable String action) {
        if (!GREETING_ACTIONS.contains(action)) {
            return unknownAction(action);
        }
        return ResponseEntity.ok(passthrough.post(robotId, "/greeting/" + action));
    }

    @GetMapping("/idle")
    public Map<String, Object> idle(@PathVariable String robotId) {
        return passthrough.get(robotId, "/idle");
    }

    @PostMapping("/idle/{action}")
    public ResponseEntity<?> idleAction(@PathVariable String robotId,
                                        @PathVariable String action) {
        if (!IDLE_ACTIONS.contains(action)) {
            return unknownAction(action);
        }
        return ResponseEntity.ok(passthrough.post(robotId, "/idle/" + action));
    }

    // ---- Power sessions (battery health) passthrough ----

    @GetMapping("/power")
    public Map<String, Object> power(@PathVariable String robotId) {
        return passthrough.get(robotId, "/power");
    }

    // ---- Adaptive polling policy passthrough ----

    @GetMapping("/polling")
    public Map<String, Object> polling(@PathVariable String robotId) {
        return passthrough.get(robotId, "/polling");
    }

    @PostMapping("/polling")
    public Map<String, Object> pollingConfig(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return passthrough.post(robotId, "/polling", body);
    }

    // ---- Senses layer passthrough ----

    @GetMapping("/senses")
    public Map<String, Object> senses(@PathVariable String robotId) {
        return passthrough.get(robotId, "/senses");
    }

    @GetMapping("/senses/samples")
    public Map<String, Object> sensesSamples(@PathVariable String robotId) {
        return passthrough.get(robotId, "/senses/samples");
    }

    @PostMapping("/senses/sniff")
    public Map<String, Object> sensesSniff(@PathVariable String robotId) {
        return passthrough.post(robotId, "/senses/sniff");
    }

    // ---- Proximity leash passthrough ----

    @GetMapping("/leash")
    public Map<String, Object> leash(@PathVariable String robotId) {
        return passthrough.get(robotId, "/leash");
    }

    @PostMapping("/leash/config")
    public Map<String, Object> leashConfig(@PathVariable String robotId,
                                           @RequestBody Map<String, Object> body) {
        return passthrough.post(robotId, "/leash/config", body);
    }

    @PostMapping("/leash/mark")
    public Map<String, Object> leashMark(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return passthrough.post(robotId, "/leash/mark", body);
    }

    // ---- Behavior framework passthrough (arbiter, behaviors, bindings) ----

    @GetMapping("/behaviors")
    public Map<String, Object> behaviors(@PathVariable String robotId) {
        return passthrough.get(robotId, "/behaviors");
    }

    @PostMapping("/behaviors")
    public Map<String, Object> upsertBehavior(@PathVariable String robotId,
                                              @RequestBody Map<String, Object> body) {
        return passthrough.post(robotId, "/behaviors", body);
    }

    @GetMapping("/behaviors/{name}")
    public Map<String, Object> behavior(@PathVariable String robotId,
                                        @PathVariable String name) {
        return passthrough.get(robotId, "/behaviors/" + name);
    }

    @GetMapping("/bindings")
    public Map<String, Object> bindings(@PathVariable String robotId) {
        return passthrough.get(robotId, "/bindings");
    }

    @PostMapping("/bindings")
    public Map<String, Object> upsertBinding(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return passthrough.post(robotId, "/bindings", body);
    }

    @GetMapping("/arbiter/status")
    public Map<String, Object> arbiterStatus(@PathVariable String robotId) {
        return passthrough.get(robotId, "/arbiter/status");
    }

    @PostMapping("/arbiter/invoke")
    public Map<String, Object> arbiterInvoke(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return passthrough.post(robotId, "/arbiter/invoke", body);
    }

    @PostMapping("/arbiter/stop")
    public Map<String, Object> arbiterStop(@PathVariable String robotId) {
        return passthrough.post(robotId, "/arbiter/stop");
    }

    private static ResponseEntity<Map<String, String>> unknownAction(String action) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "unknown_action", "action", action));
    }
}

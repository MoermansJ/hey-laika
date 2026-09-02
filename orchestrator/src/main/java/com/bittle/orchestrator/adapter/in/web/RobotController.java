package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.ExecuteAnimationUseCase;
import com.bittle.orchestrator.application.usecase.ExecuteRobotActionUseCase;
import com.bittle.orchestrator.application.usecase.GetNextBehaviorUseCase;
import com.bittle.orchestrator.application.usecase.GetRobotActivityUseCase;
import com.bittle.orchestrator.application.usecase.GetRobotAutonomousStatusUseCase;
import com.bittle.orchestrator.application.usecase.GetRobotCapabilitiesUseCase;
import com.bittle.orchestrator.application.usecase.GetRobotDisplayUseCase;
import com.bittle.orchestrator.application.usecase.GetRobotPersonalityUseCase;
import com.bittle.orchestrator.application.usecase.GetRobotStatusUseCase;
import com.bittle.orchestrator.application.usecase.GetServoStateUseCase;
import com.bittle.orchestrator.application.usecase.GetVoiceHealthUseCase;
import com.bittle.orchestrator.application.usecase.InteractWithRobotUseCase;
import com.bittle.orchestrator.application.usecase.ListAnimationsUseCase;
import com.bittle.orchestrator.application.usecase.MoveServosUseCase;
import com.bittle.orchestrator.application.usecase.PlaySoundUseCase;
import com.bittle.orchestrator.application.usecase.RelayGetToRobotUseCase;
import com.bittle.orchestrator.application.usecase.RelayPostToRobotUseCase;
import com.bittle.orchestrator.application.usecase.RelayPostWithBodyToRobotUseCase;
import com.bittle.orchestrator.application.usecase.RunVoiceDemoUseCase;
import com.bittle.orchestrator.application.usecase.SendRobotCommandUseCase;
import com.bittle.orchestrator.application.usecase.StartRobotAutonomousUseCase;
import com.bittle.orchestrator.application.usecase.StopRobotAutonomousUseCase;
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

@RestController
@RequestMapping("/api/robots/{robotId}")
public class RobotController {

    private static final Set<String> GREETING_ACTIONS = Set.of("run", "enable", "disable");
    private static final Set<String> IDLE_ACTIONS = Set.of("enable", "disable");

    private final GetRobotStatusUseCase getStatus;
    private final GetRobotPersonalityUseCase getPersonality;
    private final GetNextBehaviorUseCase getNextBehavior;
    private final SendRobotCommandUseCase sendCommand;
    private final InteractWithRobotUseCase interact;
    private final ListAnimationsUseCase listAnimations;
    private final ExecuteAnimationUseCase executeAnimation;
    private final StartRobotAutonomousUseCase startAutonomous;
    private final StopRobotAutonomousUseCase stopAutonomous;
    private final GetRobotAutonomousStatusUseCase getAutonomousStatus;
    private final GetRobotActivityUseCase getActivity;
    private final GetRobotDisplayUseCase getDisplay;
    private final GetRobotCapabilitiesUseCase getCapabilities;
    private final GetServoStateUseCase getServoState;
    private final MoveServosUseCase moveServos;
    private final RunVoiceDemoUseCase runVoiceDemo;
    private final GetVoiceHealthUseCase getVoiceHealth;
    private final PlaySoundUseCase playSound;
    private final ExecuteRobotActionUseCase executeAction;
    private final RelayGetToRobotUseCase relayGet;
    private final RelayPostToRobotUseCase relayPost;
    private final RelayPostWithBodyToRobotUseCase relayPostWithBody;

    public RobotController(GetRobotStatusUseCase getStatus,
                           GetRobotPersonalityUseCase getPersonality,
                           GetNextBehaviorUseCase getNextBehavior,
                           SendRobotCommandUseCase sendCommand,
                           InteractWithRobotUseCase interact,
                           ListAnimationsUseCase listAnimations,
                           ExecuteAnimationUseCase executeAnimation,
                           StartRobotAutonomousUseCase startAutonomous,
                           StopRobotAutonomousUseCase stopAutonomous,
                           GetRobotAutonomousStatusUseCase getAutonomousStatus,
                           GetRobotActivityUseCase getActivity,
                           GetRobotDisplayUseCase getDisplay,
                           GetRobotCapabilitiesUseCase getCapabilities,
                           GetServoStateUseCase getServoState,
                           MoveServosUseCase moveServos,
                           RunVoiceDemoUseCase runVoiceDemo,
                           GetVoiceHealthUseCase getVoiceHealth,
                           PlaySoundUseCase playSound,
                           ExecuteRobotActionUseCase executeAction,
                           RelayGetToRobotUseCase relayGet,
                           RelayPostToRobotUseCase relayPost,
                           RelayPostWithBodyToRobotUseCase relayPostWithBody) {
        this.getStatus = getStatus;
        this.getPersonality = getPersonality;
        this.getNextBehavior = getNextBehavior;
        this.sendCommand = sendCommand;
        this.interact = interact;
        this.listAnimations = listAnimations;
        this.executeAnimation = executeAnimation;
        this.startAutonomous = startAutonomous;
        this.stopAutonomous = stopAutonomous;
        this.getAutonomousStatus = getAutonomousStatus;
        this.getActivity = getActivity;
        this.getDisplay = getDisplay;
        this.getCapabilities = getCapabilities;
        this.getServoState = getServoState;
        this.moveServos = moveServos;
        this.runVoiceDemo = runVoiceDemo;
        this.getVoiceHealth = getVoiceHealth;
        this.playSound = playSound;
        this.executeAction = executeAction;
        this.relayGet = relayGet;
        this.relayPost = relayPost;
        this.relayPostWithBody = relayPostWithBody;
    }

    @GetMapping("/status")
    public RobotStatus status(@PathVariable String robotId) {
        return getStatus.execute(robotId);
    }

    @GetMapping("/personality")
    public RobotPersonality personality(@PathVariable String robotId) {
        return getPersonality.execute(robotId);
    }

    @GetMapping("/behavior")
    public RobotBehavior behavior(@PathVariable String robotId) {
        return getNextBehavior.execute(robotId);
    }

    @PostMapping("/command")
    public CommandResult command(@PathVariable String robotId,
                                 @RequestBody CommandRequest request) {
        return sendCommand.execute(robotId, request.command());
    }

    @PostMapping("/interact/{type}")
    public InteractionResult interact(@PathVariable String robotId, @PathVariable String type) {
        return interact.execute(robotId, type);
    }

    @GetMapping("/choreography/list")
    public AnimationList animations(@PathVariable String robotId) {
        return listAnimations.execute(robotId);
    }

    @PostMapping("/choreography/execute/{animation}")
    public AnimationResult executeAnimation(@PathVariable String robotId,
                                            @PathVariable String animation) {
        return executeAnimation.execute(robotId, animation);
    }

    @PostMapping("/autonomous/start")
    public AutonomousState startAutonomous(@PathVariable String robotId) {
        return startAutonomous.execute(robotId);
    }

    @PostMapping("/autonomous/stop")
    public AutonomousState stopAutonomous(@PathVariable String robotId) {
        return stopAutonomous.execute(robotId);
    }

    @GetMapping("/autonomous/status")
    public AutonomousState autonomousStatus(@PathVariable String robotId) {
        return getAutonomousStatus.execute(robotId);
    }

    @GetMapping("/activity")
    public ActivityLog activity(@PathVariable String robotId) {
        return getActivity.execute(robotId);
    }

    @GetMapping("/display")
    public DisplayContent display(@PathVariable String robotId) {
        return getDisplay.execute(robotId);
    }

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities(@PathVariable String robotId) {
        return getCapabilities.execute(robotId);
    }

    @GetMapping("/servo")
    public ServoState servoState(@PathVariable String robotId) {
        return getServoState.execute(robotId);
    }

    @PostMapping("/servo")
    public ServoMoveResult moveServos(@PathVariable String robotId,
                                      @RequestBody ServoMoveRequest request) {
        return moveServos.execute(robotId, request);
    }

    @PostMapping("/voice/demo")
    public Map<String, Object> voiceDemo(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return runVoiceDemo.execute(robotId, body);
    }

    @GetMapping("/voice/health")
    public Map<String, Object> voiceHealth(@PathVariable String robotId) {
        return getVoiceHealth.execute(robotId);
    }

    @PostMapping("/sound")
    public Map<String, Object> sound(@PathVariable String robotId,
                                     @RequestBody Map<String, Object> body) {
        return playSound.execute(robotId, body);
    }

    @PostMapping("/execute_action")
    public ActionResult executeAction(@PathVariable String robotId,
                                      @RequestBody ExecuteActionRequest request) {
        return executeAction.execute(robotId, request);
    }

    @GetMapping("/greeting")
    public Map<String, Object> greeting(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/greeting");
    }

    @PostMapping("/greeting/{action}")
    public ResponseEntity<?> greetingAction(@PathVariable String robotId,
                                            @PathVariable String action) {
        if (!GREETING_ACTIONS.contains(action)) {
            return unknownAction(action);
        }
        return ResponseEntity.ok(relayPost.execute(robotId, "/greeting/" + action));
    }

    @GetMapping("/idle")
    public Map<String, Object> idle(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/idle");
    }

    @PostMapping("/idle/{action}")
    public ResponseEntity<?> idleAction(@PathVariable String robotId,
                                        @PathVariable String action) {
        if (!IDLE_ACTIONS.contains(action)) {
            return unknownAction(action);
        }
        return ResponseEntity.ok(relayPost.execute(robotId, "/idle/" + action));
    }

    @GetMapping("/power")
    public Map<String, Object> power(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/power");
    }

    @GetMapping("/polling")
    public Map<String, Object> polling(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/polling");
    }

    @PostMapping("/polling")
    public Map<String, Object> pollingConfig(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/polling", body);
    }

    @GetMapping("/senses")
    public Map<String, Object> senses(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/senses");
    }

    @GetMapping("/senses/samples")
    public Map<String, Object> sensesSamples(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/senses/samples");
    }

    @PostMapping("/senses/sniff")
    public Map<String, Object> sensesSniff(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/senses/sniff");
    }

    @GetMapping("/leash")
    public Map<String, Object> leash(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/leash");
    }

    @PostMapping("/leash/config")
    public Map<String, Object> leashConfig(@PathVariable String robotId,
                                           @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/leash/config", body);
    }

    @PostMapping("/leash/mark")
    public Map<String, Object> leashMark(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/leash/mark", body);
    }

    @GetMapping("/behaviors")
    public Map<String, Object> behaviors(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/behaviors");
    }

    @PostMapping("/behaviors")
    public Map<String, Object> upsertBehavior(@PathVariable String robotId,
                                              @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/behaviors", body);
    }

    @GetMapping("/behaviors/{name}")
    public Map<String, Object> behavior(@PathVariable String robotId,
                                        @PathVariable String name) {
        return relayGet.execute(robotId, "/behaviors/" + name);
    }

    @GetMapping("/bindings")
    public Map<String, Object> bindings(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/bindings");
    }

    @PostMapping("/bindings")
    public Map<String, Object> upsertBinding(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/bindings", body);
    }

    @GetMapping("/arbiter/status")
    public Map<String, Object> arbiterStatus(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/arbiter/status");
    }

    @PostMapping("/arbiter/invoke")
    public Map<String, Object> arbiterInvoke(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/arbiter/invoke", body);
    }

    @PostMapping("/arbiter/stop")
    public Map<String, Object> arbiterStop(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/arbiter/stop");
    }

    private static ResponseEntity<Map<String, String>> unknownAction(String action) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "unknown_action", "action", action));
    }
}

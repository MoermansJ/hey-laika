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
import com.bittle.orchestrator.application.usecase.RelayGetBinaryFromRobotUseCase;
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
import com.bittle.orchestrator.domain.robot.BinaryContent;
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
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
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
    private final RelayGetBinaryFromRobotUseCase relayGetBinary;

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
                           RelayPostWithBodyToRobotUseCase relayPostWithBody,
                           RelayGetBinaryFromRobotUseCase relayGetBinary) {
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
        this.relayGetBinary = relayGetBinary;
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
    public Map<String, Object> sensesSamples(@PathVariable String robotId,
                                             @RequestParam Map<String, String> filters) {
        return relayGet.execute(robotId, "/senses/samples" + sampleQuery(filters));
    }

    @PostMapping("/senses/pose/reset")
    public Map<String, Object> sensesPoseReset(@PathVariable String robotId,
                                               @RequestBody(required = false) Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/senses/pose/reset",
                body == null ? Map.of() : body);
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

    @PostMapping("/abort")
    public Map<String, Object> abort(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/abort");
    }

    @GetMapping("/senses/range")
    public Map<String, Object> sensesRange(@PathVariable String robotId,
                                           @RequestParam(required = false) Integer pin) {
        return relayGet.execute(robotId, pin == null ? "/senses/range" : "/senses/range?pin=" + pin);
    }

    @GetMapping("/ears")
    public Map<String, Object> ears(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/ears");
    }

    @GetMapping("/ears/transcripts")
    public Map<String, Object> earsTranscripts(@PathVariable String robotId,
                                               @RequestParam(defaultValue = "20") int limit) {
        return relayGet.execute(robotId, "/ears/transcripts?limit=" + Math.max(1, Math.min(limit, 200)));
    }

    @PostMapping("/ears/record")
    public Map<String, Object> earsRecord(@PathVariable String robotId,
                                          @RequestBody(required = false) Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/ears/record", body == null ? Map.of() : body);
    }

    @GetMapping("/ears/vocabulary")
    public Map<String, Object> earsVocabulary(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/ears/vocabulary");
    }

    @PostMapping("/ears/vocabulary")
    public Map<String, Object> earsVocabularySet(@PathVariable String robotId,
                                                 @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/ears/vocabulary", body);
    }

    @GetMapping("/mouth")
    public Map<String, Object> mouth(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/mouth");
    }

    @PostMapping("/mouth/say")
    public Map<String, Object> mouthSay(@PathVariable String robotId,
                                        @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/mouth/say", body);
    }

    @PostMapping("/mouth/stop")
    public Map<String, Object> mouthStop(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/mouth/stop");
    }

    @GetMapping("/mouth/sounds")
    public Map<String, Object> mouthSounds(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/mouth/sounds");
    }

    @PostMapping("/mouth/play")
    public Map<String, Object> mouthPlay(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/mouth/play", body);
    }

    @GetMapping("/satellite")
    public Map<String, Object> satellite(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/satellite");
    }

    @GetMapping("/eyes")
    public Map<String, Object> eyes(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/eyes");
    }

    @GetMapping("/eyes/snap")
    public ResponseEntity<byte[]> eyesSnap(@PathVariable String robotId,
                                           @RequestParam(required = false) String fresh) {
        BinaryContent frame = relayGetBinary.execute(robotId,
                "1".equals(fresh) ? "/eyes/snap?fresh=1" : "/eyes/snap");
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(frame.contentType()))
                .cacheControl(CacheControl.noStore())
                .body(frame.body());
    }

    @PostMapping("/eyes/config")
    public Map<String, Object> eyesConfig(@PathVariable String robotId,
                                          @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/eyes/config", body);
    }

    @GetMapping("/mood")
    public Map<String, Object> mood(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/mood");
    }

    @PostMapping("/mood")
    public Map<String, Object> moodSet(@PathVariable String robotId,
                                       @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/mood", body);
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

    private static final Set<String> SAMPLE_FILTERS =
            Set.of("limit", "since", "until", "source", "minAps", "every");

    private static String sampleQuery(Map<String, String> filters) {
        String query = filters.entrySet().stream()
                .filter(e -> SAMPLE_FILTERS.contains(e.getKey()) && !e.getValue().isBlank())
                .map(e -> e.getKey() + "=" + URLEncoder.encode(e.getValue(), StandardCharsets.UTF_8))
                .collect(Collectors.joining("&"));
        return query.isEmpty() ? "" : "?" + query;
    }
}

package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.ExecuteAnimationUseCase;
import com.bittle.orchestrator.application.usecase.ExecuteRobotActionUseCase;
import com.bittle.orchestrator.application.usecase.GetActionFeedUseCase;
import com.bittle.orchestrator.application.usecase.GetFruitflyStatusUseCase;
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
import com.bittle.orchestrator.domain.robot.ActionFeed;
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
import com.bittle.orchestrator.domain.robot.FruitflyStatus;
import com.bittle.orchestrator.domain.robot.InteractionResult;
import com.bittle.orchestrator.domain.robot.RobotBehavior;
import com.bittle.orchestrator.domain.robot.RobotPersonality;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import com.bittle.orchestrator.domain.robot.ServoMoveRequest;
import com.bittle.orchestrator.domain.robot.ServoMoveResult;
import com.bittle.orchestrator.domain.robot.ServoState;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
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
@Tag(name = "Robot", description = "One robot's hardware, brain relays and senses, addressed through its adapter")
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
    private final GetFruitflyStatusUseCase getFruitflyStatus;
    private final GetActionFeedUseCase getActionFeed;
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
                           GetFruitflyStatusUseCase getFruitflyStatus,
                           GetActionFeedUseCase getActionFeed,
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
        this.getFruitflyStatus = getFruitflyStatus;
        this.getActionFeed = getActionFeed;
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

    @Operation(summary = "Robot status",
            description = "Hardware, battery and connection state as the adapter reports it.")
    @GetMapping("/status")
    public RobotStatus status(@PathVariable String robotId) {
        return getStatus.execute(robotId);
    }

    @Operation(summary = "Adapter-side personality state")
    @Deprecated
    @GetMapping("/personality")
    public RobotPersonality personality(@PathVariable String robotId) {
        return getPersonality.execute(robotId);
    }

    @Operation(summary = "One behavior decision from the adapter's own engine",
            description = "Ollama by default, Claude opt-in.")
    @Deprecated
    @GetMapping("/behavior")
    public RobotBehavior behavior(@PathVariable String robotId) {
        return getNextBehavior.execute(robotId);
    }

    @Operation(summary = "Send a raw controller command")
    @PostMapping("/command")
    public CommandResult command(@PathVariable String robotId,
                                 @RequestBody CommandRequest request) {
        return sendCommand.execute(robotId, request.command());
    }

    @Operation(summary = "Log an interaction",
            description = "Types: pet, play, talk, feed.")
    @Deprecated
    @PostMapping("/interact/{type}")
    public InteractionResult interact(@PathVariable String robotId, @PathVariable String type) {
        return interact.execute(robotId, type);
    }

    @Operation(summary = "Available animations")
    @GetMapping("/choreography/list")
    public AnimationList animations(@PathVariable String robotId) {
        return listAnimations.execute(robotId);
    }

    @Operation(summary = "Run an animation")
    @PostMapping("/choreography/execute/{animation}")
    public AnimationResult executeAnimation(@PathVariable String robotId,
                                            @PathVariable String animation) {
        return executeAnimation.execute(robotId, animation);
    }

    @Operation(summary = "Start the adapter's legacy autonomous loop")
    @Deprecated
    @PostMapping("/autonomous/start")
    public AutonomousState startAutonomous(@PathVariable String robotId) {
        return startAutonomous.execute(robotId);
    }

    @Operation(summary = "Stop the adapter's legacy autonomous loop")
    @Deprecated
    @PostMapping("/autonomous/stop")
    public AutonomousState stopAutonomous(@PathVariable String robotId) {
        return stopAutonomous.execute(robotId);
    }

    @Operation(summary = "State of the adapter's legacy autonomous loop")
    @Deprecated
    @GetMapping("/autonomous/status")
    public AutonomousState autonomousStatus(@PathVariable String robotId) {
        return getAutonomousStatus.execute(robotId);
    }

    @Operation(summary = "Recent activity log")
    @GetMapping("/activity")
    public ActivityLog activity(@PathVariable String robotId) {
        return getActivity.execute(robotId);
    }

    @Operation(summary = "Per-action feed",
            description = "Every step the arbiter dispatched, newest first, tagged with the mode "
                    + "that generated it — a finer grain than the behavior run log, and the only "
                    + "place a continuous generator's individual decisions appear.")
    @GetMapping("/actions/feed")
    public ActionFeed actionFeed(@PathVariable String robotId,
                                 @RequestParam(defaultValue = "20") int limit) {
        return getActionFeed.execute(robotId, limit);
    }

    @Operation(summary = "Fruitfly's last decoded command",
            description = "Observability only — read-only snapshot of fruitfly_drive.py's last "
                    + "decoded state; the arbiter submission it drove has already happened by the "
                    + "time this is read.")
    @GetMapping("/fruitfly/status")
    public FruitflyStatus fruitflyStatus(@PathVariable String robotId) {
        return getFruitflyStatus.execute(robotId);
    }

    @Operation(summary = "What the robot is currently saying")
    @Deprecated
    @GetMapping("/display")
    public DisplayContent display(@PathVariable String robotId) {
        return getDisplay.execute(robotId);
    }

    @Operation(summary = "Adapter capability schema",
            description = "Servos, actions and moves; the console builds its controls from it.")
    @GetMapping("/capabilities")
    public Map<String, Object> capabilities(@PathVariable String robotId) {
        return getCapabilities.execute(robotId);
    }

    @Operation(summary = "Commanded joint angles")
    @GetMapping("/servo")
    public ServoState servoState(@PathVariable String robotId) {
        return getServoState.execute(robotId);
    }

    @Operation(summary = "Move joints")
    @PostMapping("/servo")
    public ServoMoveResult moveServos(@PathVariable String robotId,
                                      @RequestBody ServoMoveRequest request) {
        return moveServos.execute(robotId, request);
    }

    @Operation(summary = "Text-in voice chain",
            description = "LLM reply plus buzzer feedback.")
    @PostMapping("/voice/demo")
    public Map<String, Object> voiceDemo(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return runVoiceDemo.execute(robotId, body);
    }

    @Operation(summary = "Ollama reachability and model availability")
    @GetMapping("/voice/health")
    public Map<String, Object> voiceHealth(@PathVariable String robotId) {
        return getVoiceHealth.execute(robotId);
    }

    @Operation(summary = "Play a buzzer tone sequence")
    @PostMapping("/sound")
    public Map<String, Object> sound(@PathVariable String robotId,
                                     @RequestBody Map<String, Object> body) {
        return playSound.execute(robotId, body);
    }

    @Operation(summary = "Execute a named high-level action",
            description = "409 behavior_loop_running while the orchestrator loop drives this robot.")
    @PostMapping("/execute_action")
    public ActionResult executeAction(@PathVariable String robotId,
                                      @RequestBody ExecuteActionRequest request) {
        return executeAction.execute(robotId, request);
    }

    @Operation(summary = "Boot-greeting status",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/greeting")
    public Map<String, Object> greeting(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/greeting");
    }

    @Operation(summary = "Run, enable or disable the boot greeting",
            description = "Relayed to the same path on the adapter. Other action names yield 400 unknown_action.")
    @PostMapping("/greeting/{action}")
    public ResponseEntity<?> greetingAction(@PathVariable String robotId,
                                            @PathVariable String action) {
        if (!GREETING_ACTIONS.contains(action)) {
            return unknownAction(action);
        }
        return ResponseEntity.ok(relayPost.execute(robotId, "/greeting/" + action));
    }

    @Operation(summary = "Idle-ladder status",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/idle")
    public Map<String, Object> idle(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/idle");
    }

    @Operation(summary = "Enable or disable the idle ladder",
            description = "Relayed to the same path on the adapter. Other action names yield 400 unknown_action.")
    @PostMapping("/idle/{action}")
    public ResponseEntity<?> idleAction(@PathVariable String robotId,
                                        @PathVariable String action) {
        if (!IDLE_ACTIONS.contains(action)) {
            return unknownAction(action);
        }
        return ResponseEntity.ok(relayPost.execute(robotId, "/idle/" + action));
    }

    @Operation(summary = "Power-session tracker",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/power")
    public Map<String, Object> power(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/power");
    }

    @Operation(summary = "Battery saver tier, overrides and thresholds",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/power/saver")
    public Map<String, Object> powerSaver(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/power/saver");
    }

    @Operation(summary = "Override the battery saver tier",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/power/saver")
    public Map<String, Object> powerSaverOverride(@PathVariable String robotId,
                                                  @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/power/saver", body);
    }

    @Operation(summary = "Configure the battery saver thresholds",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/power/saver/config")
    public Map<String, Object> powerSaverConfig(@PathVariable String robotId,
                                                @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/power/saver/config", body);
    }

    @Operation(summary = "Adaptive telemetry polling policy",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/polling")
    public Map<String, Object> polling(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/polling");
    }

    @Operation(summary = "Configure the adaptive telemetry polling policy",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/polling")
    public Map<String, Object> pollingConfig(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/polling", body);
    }

    @Operation(summary = "Senses layer status",
            description = "Relayed to the same path on the adapter. WiFi sniffer and dead-reckoned pose.")
    @GetMapping("/senses")
    public Map<String, Object> senses(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/senses");
    }

    @Operation(summary = "Recent sense samples",
            description = "Relayed to the same path on the adapter. Filters: limit, since, until, source, minAps, every.")
    @GetMapping("/senses/samples")
    public Map<String, Object> sensesSamples(@PathVariable String robotId,
                                             @RequestParam Map<String, String> filters) {
        return relayGet.execute(robotId, "/senses/samples" + sampleQuery(filters));
    }

    @Operation(summary = "Reset the dead-reckoned pose",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/senses/pose/reset")
    public Map<String, Object> sensesPoseReset(@PathVariable String robotId,
                                               @RequestBody(required = false) Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/senses/pose/reset",
                body == null ? Map.of() : body);
    }

    @Operation(summary = "Trigger one WiFi scan now",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/senses/sniff")
    public Map<String, Object> sensesSniff(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/senses/sniff");
    }

    @Operation(summary = "Newest sensor-loop reading",
            description = "Relayed to the same path on the adapter. Range ahead, pose, IMU yaw, battery,"
                    + " the command in flight. fresh=1 takes a reading now.")
    @GetMapping("/sensors/latest")
    public Map<String, Object> sensorsLatest(@PathVariable String robotId,
                                             @RequestParam(required = false) String fresh) {
        return relayGet.execute(robotId, "1".equals(fresh) ? "/sensors/latest?fresh=1" : "/sensors/latest");
    }

    @Operation(summary = "Recent sensor readings",
            description = "Relayed to the same path on the adapter. Filters: limit, since, stored=1 (SQLite"
                    + " instead of the ring buffer).")
    @GetMapping("/sensors/recent")
    public Map<String, Object> sensorsRecent(@PathVariable String robotId,
                                             @RequestParam Map<String, String> filters) {
        return relayGet.execute(robotId, "/sensors/recent" + query(filters, READING_FILTERS));
    }

    @Operation(summary = "Navigation status",
            description = "Relayed to the same path on the adapter. Route state, target, avoidance,"
                    + " sensor loop, map and error summary.")
    @GetMapping("/navigation")
    public Map<String, Object> navigation(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/navigation");
    }

    @Operation(summary = "Tune navigation",
            description = "Relayed to the same path on the adapter. stopCm, sensorHz, avoidanceEnabled,"
                    + " sweepAngles and the other navigator settings.")
    @PostMapping("/navigation/config")
    public Map<String, Object> navigationConfig(@PathVariable String robotId,
                                                @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/navigation/config", body);
    }

    @Operation(summary = "Navigate to a map position",
            description = "Relayed to the same path on the adapter. Body {x, y} in metres in the map frame;"
                    + " 409 while an error waits for an answer or in away mode.")
    @PostMapping("/navigation/target")
    public Map<String, Object> navigationTarget(@PathVariable String robotId,
                                                @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/navigation/target", body);
    }

    @Operation(summary = "Cancel the current route",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/navigation/cancel")
    public Map<String, Object> navigationCancel(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/navigation/cancel");
    }

    @Operation(summary = "Occupancy grid",
            description = "Relayed to the same path on the adapter. Cells as [cx, cy, f|o, logodds] with the"
                    + " pose, target and route for the Map tab.")
    @GetMapping("/navigation/map")
    public Map<String, Object> navigationMap(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/navigation/map");
    }

    @Operation(summary = "Clear the occupancy grid",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/navigation/map/reset")
    public Map<String, Object> navigationMapReset(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/navigation/map/reset");
    }

    @Operation(summary = "Correct one map cell",
            description = "Relayed to the same path on the adapter. Body {cx, cy, state: free|occupied|unknown}.")
    @PostMapping("/navigation/map/cell")
    public Map<String, Object> navigationMapCell(@PathVariable String robotId,
                                                 @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/navigation/map/cell", body);
    }

    @Operation(summary = "Sonar sweep with the head",
            description = "Relayed to the same path on the adapter. A head-pan range scan from where she"
                    + " stands, run as an arbiter behavior.")
    @PostMapping("/navigation/sweep")
    public Map<String, Object> navigationSweep(@PathVariable String robotId,
                                               @RequestBody(required = false) Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/navigation/sweep", body == null ? Map.of() : body);
    }

    @Operation(summary = "Run a skill with avoidance stood down",
            description = "Relayed to the same path on the adapter. Body {behavior} or {command, settleS};"
                    + " reactive avoidance resumes when the run ends.")
    @PostMapping("/navigation/override")
    public Map<String, Object> navigationOverride(@PathVariable String robotId,
                                                  @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/navigation/override", body);
    }

    @Operation(summary = "Navigation errors",
            description = "Relayed to the same path on the adapter. The error waiting for an answer, retry"
                    + " streaks and the history.")
    @GetMapping("/navigation/errors")
    public Map<String, Object> navigationErrors(@PathVariable String robotId,
                                                @RequestParam(required = false) Integer limit) {
        return relayGet.execute(robotId, limit == null ? "/navigation/errors"
                : "/navigation/errors?limit=" + limit);
    }

    @Operation(summary = "Answer the error state",
            description = "Relayed to the same path on the adapter. Body {choice: trust_map|trust_sensor|manual,"
                    + " note}.")
    @PostMapping("/navigation/errors/respond")
    public Map<String, Object> navigationErrorsRespond(@PathVariable String robotId,
                                                       @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/navigation/errors/respond", body);
    }

    @Operation(summary = "Export training data",
            description = "Relayed to the same path on the adapter. kind=actions|readings, format=csv|json,"
                    + " since (epoch seconds), limit.")
    @ApiResponse(responseCode = "200", content = {
            @Content(mediaType = MediaType.APPLICATION_JSON_VALUE),
            @Content(mediaType = "text/csv", schema = @Schema(type = "string"))})
    @GetMapping("/navigation/data/export")
    public ResponseEntity<byte[]> navigationDataExport(@PathVariable String robotId,
                                                       @RequestParam Map<String, String> filters) {
        BinaryContent content = relayGetBinary.execute(robotId,
                "/navigation/data/export" + query(filters, EXPORT_FILTERS));
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(content.contentType()))
                .cacheControl(CacheControl.noStore())
                .body(content.body());
    }

    @Operation(summary = "Roaming Assistant's collection points",
            description = "Relayed to the same path on the adapter. Filters: limit, since, until.")
    @GetMapping("/collection_points")
    public Map<String, Object> collectionPoints(@PathVariable String robotId,
                                                @RequestParam Map<String, String> filters) {
        return relayGet.execute(robotId, "/collection_points" + query(filters, COLLECTION_POINT_FILTERS));
    }

    @Operation(summary = "A collection point's photo",
            description = "Relayed to the same path on the adapter.")
    @ApiResponse(responseCode = "200", content = @Content(mediaType = MediaType.IMAGE_JPEG_VALUE,
            schema = @Schema(type = "string", format = "binary")))
    @GetMapping("/collection_points/{pointId}/photo")
    public ResponseEntity<byte[]> collectionPointPhoto(@PathVariable String robotId,
                                                       @PathVariable String pointId) {
        BinaryContent photo = relayGetBinary.execute(robotId, "/collection_points/" + pointId + "/photo");
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(photo.contentType()))
                .cacheControl(CacheControl.noStore())
                .body(photo.body());
    }

    @Operation(summary = "Proximity-leash state",
            description = "Relayed to the same path on the adapter. RSSI, zone and dead-man.")
    @GetMapping("/leash")
    public Map<String, Object> leash(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/leash");
    }

    @Operation(summary = "Leash thresholds and enable",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/leash/config")
    public Map<String, Object> leashConfig(@PathVariable String robotId,
                                           @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/leash/config", body);
    }

    @Operation(summary = "Record a labelled RSSI mark",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/leash/mark")
    public Map<String, Object> leashMark(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/leash/mark", body);
    }

    @Operation(summary = "List stored behaviors",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/behaviors")
    public Map<String, Object> behaviors(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/behaviors");
    }

    @Operation(summary = "Upsert a stored behavior",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/behaviors")
    public Map<String, Object> upsertBehavior(@PathVariable String robotId,
                                              @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/behaviors", body);
    }

    @Operation(summary = "One stored behavior",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/behaviors/{name}")
    public Map<String, Object> behavior(@PathVariable String robotId,
                                        @PathVariable String name) {
        return relayGet.execute(robotId, "/behaviors/" + name);
    }

    @Operation(summary = "List event bindings",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/bindings")
    public Map<String, Object> bindings(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/bindings");
    }

    @Operation(summary = "Upsert an event binding",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/bindings")
    public Map<String, Object> upsertBinding(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/bindings", body);
    }

    @Operation(summary = "Stop the current motion immediately",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/abort")
    public Map<String, Object> abort(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/abort");
    }

    @Operation(summary = "One-shot ultrasonic read",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/senses/range")
    public Map<String, Object> sensesRange(@PathVariable String robotId,
                                           @RequestParam(required = false) Integer pin) {
        return relayGet.execute(robotId, pin == null ? "/senses/range" : "/senses/range?pin=" + pin);
    }

    @Operation(summary = "Satellite microphone status",
            description = "Relayed to the same path on the adapter. Includes the live level and the custom vocabulary.")
    @GetMapping("/ears")
    public Map<String, Object> ears(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/ears");
    }

    @Operation(summary = "Recent transcripts",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/ears/transcripts")
    public Map<String, Object> earsTranscripts(@PathVariable String robotId,
                                               @RequestParam(defaultValue = "20") int limit) {
        return relayGet.execute(robotId, "/ears/transcripts?limit=" + Math.max(1, Math.min(limit, 200)));
    }

    @Operation(summary = "Conversation state and recent turns",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/conversation")
    public Map<String, Object> conversation(@PathVariable String robotId,
                                            @RequestParam(defaultValue = "10") int limit) {
        return relayGet.execute(robotId, "/conversation?limit=" + Math.max(1, Math.min(limit, 100)));
    }

    @Operation(summary = "A typed conversation turn",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/conversation/say")
    public Map<String, Object> conversationSay(@PathVariable String robotId,
                                               @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/conversation/say", body);
    }

    @Operation(summary = "Start a conversation turn from the console",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/conversation/listen")
    public Map<String, Object> conversationListen(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/conversation/listen");
    }

    @Operation(summary = "Cancel the current conversation turn",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/conversation/cancel")
    public Map<String, Object> conversationCancel(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/conversation/cancel");
    }

    @Operation(summary = "The conversation prompt template",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/conversation/prompt")
    public Map<String, Object> conversationPrompt(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/conversation/prompt");
    }

    @Operation(summary = "Replace the conversation prompt template",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/conversation/prompt")
    public Map<String, Object> conversationPromptSet(@PathVariable String robotId,
                                                     @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/conversation/prompt", body);
    }

    @Operation(summary = "Record a phrase from the live microphone",
            description = "Relayed to the same path on the adapter. Returns the transcript and whether it matched the wake phrase; never fires the voice event.")
    @PostMapping("/ears/record")
    public Map<String, Object> earsRecord(@PathVariable String robotId,
                                          @RequestBody(required = false) Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/ears/record", body == null ? Map.of() : body);
    }

    @Operation(summary = "Extra phrases whisper is primed with and accepted spellings of the name",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/ears/vocabulary")
    public Map<String, Object> earsVocabulary(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/ears/vocabulary");
    }

    @Operation(summary = "Set the extra phrases and name spellings",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/ears/vocabulary")
    public Map<String, Object> earsVocabularySet(@PathVariable String robotId,
                                                 @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/ears/vocabulary", body);
    }

    @Operation(summary = "Speaker status",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/mouth")
    public Map<String, Object> mouth(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/mouth");
    }

    @Operation(summary = "Speak text on the dog",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/mouth/say")
    public Map<String, Object> mouthSay(@PathVariable String robotId,
                                        @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/mouth/say", body);
    }

    @Operation(summary = "espeak-ng voices and variants",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/mouth/voices")
    public Map<String, Object> mouthVoices(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/mouth/voices");
    }

    @Operation(summary = "Choose the speaking voice",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/mouth/voice")
    public Map<String, Object> mouthVoice(@PathVariable String robotId,
                                          @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/mouth/voice", body);
    }

    @Operation(summary = "Stop playback",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/mouth/stop")
    public Map<String, Object> mouthStop(@PathVariable String robotId) {
        return relayPost.execute(robotId, "/mouth/stop");
    }

    @Operation(summary = "Clip library on the dog's speaker",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/mouth/sounds")
    public Map<String, Object> mouthSounds(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/mouth/sounds");
    }

    @Operation(summary = "Play a clip",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/mouth/play")
    public Map<String, Object> mouthPlay(@PathVariable String robotId,
                                         @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/mouth/play", body);
    }

    @Operation(summary = "The XIAO satellite's own status",
            description = "Relayed to the same path on the adapter. Mic, camera, rssi and led.")
    @GetMapping("/satellite")
    public Map<String, Object> satellite(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/satellite");
    }

    @Operation(summary = "Camera and person-detection status",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/eyes")
    public Map<String, Object> eyes(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/eyes");
    }

    @Operation(summary = "Latest cached camera frame",
            description = "Relayed to the same path on the adapter. fresh=1 grabs a new frame.")
    @ApiResponse(responseCode = "200", content = @Content(mediaType = MediaType.IMAGE_JPEG_VALUE,
            schema = @Schema(type = "string", format = "binary")))
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

    @Operation(summary = "Pause or resume frame grabbing",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/eyes/config")
    public Map<String, Object> eyesConfig(@PathVariable String robotId,
                                          @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/eyes/config", body);
    }

    @Operation(summary = "Mood light state, palette and badge colours",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/mood")
    public Map<String, Object> mood(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/mood");
    }

    @Operation(summary = "Pin, flash or set a custom mood colour",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/mood")
    public Map<String, Object> moodSet(@PathVariable String robotId,
                                       @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/mood", body);
    }

    @Operation(summary = "What the motion arbiter is running",
            description = "Relayed to the same path on the adapter.")
    @GetMapping("/arbiter/status")
    public Map<String, Object> arbiterStatus(@PathVariable String robotId) {
        return relayGet.execute(robotId, "/arbiter/status");
    }

    @Operation(summary = "Submit a behavior to the arbiter",
            description = "Relayed to the same path on the adapter.")
    @PostMapping("/arbiter/invoke")
    public Map<String, Object> arbiterInvoke(@PathVariable String robotId,
                                             @RequestBody Map<String, Object> body) {
        return relayPostWithBody.execute(robotId, "/arbiter/invoke", body);
    }

    @Operation(summary = "Stop the arbiter's current behavior",
            description = "Relayed to the same path on the adapter.")
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
    private static final Set<String> READING_FILTERS =
            Set.of("limit", "since", "stored", "format");
    private static final Set<String> EXPORT_FILTERS =
            Set.of("limit", "since", "kind", "format");
    private static final Set<String> COLLECTION_POINT_FILTERS =
            Set.of("limit", "since", "until");

    private static String sampleQuery(Map<String, String> filters) {
        return query(filters, SAMPLE_FILTERS);
    }

    private static String query(Map<String, String> filters, Set<String> allowed) {
        String query = filters.entrySet().stream()
                .filter(e -> allowed.contains(e.getKey()) && !e.getValue().isBlank())
                .map(e -> e.getKey() + "=" + URLEncoder.encode(e.getValue(), StandardCharsets.UTF_8))
                .collect(Collectors.joining("&"));
        return query.isEmpty() ? "" : "?" + query;
    }
}

package com.bittle.orchestrator.client;

import com.bittle.orchestrator.dto.Dtos.ActionResult;
import com.bittle.orchestrator.dto.Dtos.ActivityLog;
import com.bittle.orchestrator.dto.Dtos.AnimationList;
import com.bittle.orchestrator.dto.Dtos.AnimationResult;
import com.bittle.orchestrator.dto.Dtos.AutonomousState;
import com.bittle.orchestrator.dto.Dtos.CommandRequest;
import com.bittle.orchestrator.dto.Dtos.CommandResult;
import com.bittle.orchestrator.dto.Dtos.DisplayContent;
import com.bittle.orchestrator.dto.Dtos.ExecuteActionRequest;
import com.bittle.orchestrator.dto.Dtos.InteractionResult;
import com.bittle.orchestrator.dto.Dtos.RobotBehavior;
import com.bittle.orchestrator.dto.Dtos.RobotPersonality;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.dto.Dtos.ServoMoveRequest;
import com.bittle.orchestrator.dto.Dtos.ServoMoveResult;
import com.bittle.orchestrator.dto.Dtos.ServoState;
import com.bittle.orchestrator.exception.AdapterErrorException;
import com.bittle.orchestrator.exception.AdapterUnavailableException;
import java.util.Map;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/**
 * HTTP client for the Python robot adapter services. The adapters expose a
 * generic robot-scoped API (/api/robots/{robotId}/...); which physical robot
 * answers is determined purely by which service URL is called.
 */
@Service
public class PythonServiceClient {

    private final RestClient http;

    public PythonServiceClient(RestClient pythonRestClient) {
        this.http = pythonRestClient;
    }

    public Map<String, Object> health(String serviceUrl) {
        return exchange(() -> http.get().uri(serviceUrl + "/api/health")
                .retrieve().body(Map.class));
    }

    public RobotStatus status(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/status"))
                .retrieve().body(RobotStatus.class));
    }

    public RobotPersonality personality(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/personality"))
                .retrieve().body(RobotPersonality.class));
    }

    public RobotBehavior nextBehavior(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/behavior"))
                .retrieve().body(RobotBehavior.class));
    }

    public CommandResult command(String serviceUrl, String robotId, String command) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/command"))
                .body(new CommandRequest(command))
                .retrieve().body(CommandResult.class));
    }

    public InteractionResult interact(String serviceUrl, String robotId, String type) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/interact/" + type))
                .retrieve().body(InteractionResult.class));
    }

    public AnimationList animations(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/choreography/list"))
                .retrieve().body(AnimationList.class));
    }

    public AnimationResult executeAnimation(String serviceUrl, String robotId, String animation) {
        return exchange(() -> http.post()
                .uri(robotUri(serviceUrl, robotId, "/choreography/execute/" + animation))
                .retrieve().body(AnimationResult.class));
    }

    public AutonomousState startAutonomous(String serviceUrl, String robotId) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/autonomous/start"))
                .retrieve().body(AutonomousState.class));
    }

    public AutonomousState stopAutonomous(String serviceUrl, String robotId) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/autonomous/stop"))
                .retrieve().body(AutonomousState.class));
    }

    public AutonomousState autonomousStatus(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/autonomous/status"))
                .retrieve().body(AutonomousState.class));
    }

    public ActivityLog activity(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/activity"))
                .retrieve().body(ActivityLog.class));
    }

    public ActionResult executeAction(String serviceUrl, String robotId,
                                      ExecuteActionRequest request) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/execute_action"))
                .body(request)
                .retrieve().body(ActionResult.class));
    }

    public DisplayContent display(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/display"))
                .retrieve().body(DisplayContent.class));
    }

    /** The adapter's capability schema, passed through untyped so new
     *  capability kinds don't require orchestrator releases. */
    public Map<String, Object> capabilities(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/schema"))
                .retrieve().body(Map.class));
    }

    public ServoState servoState(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/servo"))
                .retrieve().body(ServoState.class));
    }

    public ServoMoveResult moveServos(String serviceUrl, String robotId,
                                      ServoMoveRequest request) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/servo"))
                .body(request)
                .retrieve().body(ServoMoveResult.class));
    }

    /** Voice MVP endpoints — untyped passthrough like capabilities. */
    public Map<String, Object> voiceDemo(String serviceUrl, String robotId,
                                         Map<String, Object> body) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/voice/demo"))
                .body(body)
                .retrieve().body(Map.class));
    }

    public Map<String, Object> voiceHealth(String serviceUrl, String robotId) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, "/voice/health"))
                .retrieve().body(Map.class));
    }

    public Map<String, Object> sound(String serviceUrl, String robotId,
                                     Map<String, Object> body) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, "/sound"))
                .body(body)
                .retrieve().body(Map.class));
    }

    /** Untyped passthrough for host-side lifecycle behaviors (greeting/idle). */
    public Map<String, Object> lifecycleGet(String serviceUrl, String robotId,
                                            String path) {
        return exchange(() -> http.get().uri(robotUri(serviceUrl, robotId, path))
                .retrieve().body(Map.class));
    }

    public Map<String, Object> lifecyclePost(String serviceUrl, String robotId,
                                             String path) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, path))
                .retrieve().body(Map.class));
    }

    public Map<String, Object> lifecyclePostBody(String serviceUrl, String robotId,
                                                 String path,
                                                 Map<String, Object> body) {
        return exchange(() -> http.post().uri(robotUri(serviceUrl, robotId, path))
                .body(body)
                .retrieve().body(Map.class));
    }

    private static String robotUri(String serviceUrl, String robotId, String path) {
        return serviceUrl + "/api/robots/" + robotId + path;
    }

    private <T> T exchange(Supplier<T> call) {
        try {
            return call.get();
        } catch (RestClientResponseException e) {
            throw new AdapterErrorException(e.getStatusCode().value(),
                    e.getResponseBodyAsString());
        } catch (ResourceAccessException e) {
            throw new AdapterUnavailableException(e.getMessage(), e);
        }
    }
}

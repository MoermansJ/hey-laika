package com.bittle.orchestrator.adapter.out.http;

import com.bittle.orchestrator.application.port.out.AdapterErrorException;
import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Robot;
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
import java.util.function.Supplier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/**
 * HTTP client for the Python robot adapter services. The adapters expose a
 * generic robot-scoped API (/api/robots/{robotId}/...); which physical robot
 * answers is determined purely by which service URL is called.
 */
@Component
public class PythonAdapterHttpClient implements RobotAdapterPort {

    private final RestClient http;

    public PythonAdapterHttpClient(RestClient pythonRestClient) {
        this.http = pythonRestClient;
    }

    @Override
    public Map<String, Object> metrics(Robot robot) {
        return exchange(() -> http.get().uri(robot.serviceUrl() + "/metrics")
                .retrieve().body(Map.class));
    }

    @Override
    public RobotStatus status(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/status"))
                .retrieve().body(RobotStatus.class));
    }

    @Override
    public RobotPersonality personality(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/personality"))
                .retrieve().body(RobotPersonality.class));
    }

    @Override
    public RobotBehavior nextBehavior(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/behavior"))
                .retrieve().body(RobotBehavior.class));
    }

    @Override
    public CommandResult command(Robot robot, String command) {
        return exchange(() -> http.post().uri(robotUri(robot, "/command"))
                .body(new CommandRequest(command))
                .retrieve().body(CommandResult.class));
    }

    @Override
    public InteractionResult interact(Robot robot, String type) {
        return exchange(() -> http.post().uri(robotUri(robot, "/interact/" + type))
                .retrieve().body(InteractionResult.class));
    }

    @Override
    public AnimationList animations(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/choreography/list"))
                .retrieve().body(AnimationList.class));
    }

    @Override
    public AnimationResult executeAnimation(Robot robot, String animation) {
        return exchange(() -> http.post()
                .uri(robotUri(robot, "/choreography/execute/" + animation))
                .retrieve().body(AnimationResult.class));
    }

    @Override
    public AutonomousState startAutonomous(Robot robot) {
        return exchange(() -> http.post().uri(robotUri(robot, "/autonomous/start"))
                .retrieve().body(AutonomousState.class));
    }

    @Override
    public AutonomousState stopAutonomous(Robot robot) {
        return exchange(() -> http.post().uri(robotUri(robot, "/autonomous/stop"))
                .retrieve().body(AutonomousState.class));
    }

    @Override
    public AutonomousState autonomousStatus(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/autonomous/status"))
                .retrieve().body(AutonomousState.class));
    }

    @Override
    public ActivityLog activity(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/activity"))
                .retrieve().body(ActivityLog.class));
    }

    @Override
    public ActionResult executeAction(Robot robot, ExecuteActionRequest request) {
        return exchange(() -> http.post().uri(robotUri(robot, "/execute_action"))
                .body(request)
                .retrieve().body(ActionResult.class));
    }

    @Override
    public DisplayContent display(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/display"))
                .retrieve().body(DisplayContent.class));
    }

    @Override
    public Map<String, Object> capabilities(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/schema"))
                .retrieve().body(Map.class));
    }

    @Override
    public ServoState servoState(Robot robot) {
        return exchange(() -> http.get().uri(robotUri(robot, "/servo"))
                .retrieve().body(ServoState.class));
    }

    @Override
    public ServoMoveResult moveServos(Robot robot, ServoMoveRequest request) {
        return exchange(() -> http.post().uri(robotUri(robot, "/servo"))
                .body(request)
                .retrieve().body(ServoMoveResult.class));
    }

    @Override
    public Map<String, Object> voiceDemo(Robot robot, Map<String, Object> body) {
        return post(robot, "/voice/demo", body);
    }

    @Override
    public Map<String, Object> voiceHealth(Robot robot) {
        return get(robot, "/voice/health");
    }

    @Override
    public Map<String, Object> sound(Robot robot, Map<String, Object> body) {
        return post(robot, "/sound", body);
    }

    @Override
    public Map<String, Object> get(Robot robot, String path) {
        return exchange(() -> http.get().uri(robotUri(robot, path))
                .retrieve().body(Map.class));
    }

    @Override
    public Map<String, Object> post(Robot robot, String path) {
        return exchange(() -> http.post().uri(robotUri(robot, path))
                .retrieve().body(Map.class));
    }

    @Override
    public Map<String, Object> post(Robot robot, String path, Map<String, Object> body) {
        return exchange(() -> http.post().uri(robotUri(robot, path))
                .body(body)
                .retrieve().body(Map.class));
    }

    private static String robotUri(Robot robot, String path) {
        return robot.serviceUrl() + "/api/robots/" + robot.id() + path;
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

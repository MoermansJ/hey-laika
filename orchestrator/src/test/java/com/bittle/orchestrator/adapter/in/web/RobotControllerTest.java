package com.bittle.orchestrator.adapter.in.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.in.RobotOperationsUseCase;
import com.bittle.orchestrator.application.port.in.RobotPassthroughUseCase;
import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import com.bittle.orchestrator.domain.robot.ServoJoint;
import com.bittle.orchestrator.domain.robot.ServoMoveResult;
import com.bittle.orchestrator.domain.robot.ServoState;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

@WebMvcTest(RobotController.class)
class RobotControllerTest {

    private static final String SIT_DOWN_REQUEST =
            "{\"action\":\"sit_down\",\"durationMs\":1500,\"sequenceId\":1}";

    @Autowired
    private MockMvcTester mvc;

    @MockitoBean
    private RobotOperationsUseCase robots;

    @MockitoBean
    private RobotPassthroughUseCase passthrough;

    @MockitoBean
    private OrchestratorMetricsPort metrics;

    @Test
    void givenLoopStopped_whenExecuteActionPosted_thenItIsProxiedToTheAgent() {
        when(robots.executeAction(eq("bittle-1"), any()))
                .thenReturn(new ActionResult("bittle-1", "sit_down", true, 1500L, "executed"));

        var result = mvc.post().uri("/api/robots/bittle-1/execute_action")
                .contentType(MediaType.APPLICATION_JSON)
                .content(SIT_DOWN_REQUEST)
                .exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.success").isEqualTo(true);
    }

    @Test
    void givenLoopRunning_whenExecuteActionPosted_thenConflictIsReturned() {
        when(robots.executeAction(eq("bittle-1"), any()))
                .thenThrow(new BehaviorLoopRunningException());

        var result = mvc.post().uri("/api/robots/bittle-1/execute_action")
                .contentType(MediaType.APPLICATION_JSON)
                .content(SIT_DOWN_REQUEST)
                .exchange();

        assertThat(result).hasStatus(HttpStatus.CONFLICT)
                .bodyJson().extractingPath("$.error").isEqualTo("behavior_loop_running");
    }

    @Test
    void givenRegisteredRobot_whenStatusRequested_thenAgentStatusIsProxied() {
        when(robots.status("bittle-1"))
                .thenReturn(new RobotStatus("bittle-1", true, "mock", "kbalance", 5, false,
                        "happy", 87.5, "strong", 120L, 1000.0));

        var result = mvc.get().uri("/api/robots/bittle-1/status").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().isLenientlyEqualTo("""
                        {"robotId": "bittle-1", "connected": true, "mood": "happy"}
                        """);
    }

    @Test
    void givenRegisteredRobot_whenCapabilitiesRequested_thenTheyArePassedThroughUntyped() {
        when(robots.capabilities("bittle-1")).thenReturn(Map.of(
                "robotId", "bittle-1",
                "schema", Map.of("servos", List.of(Map.of("index", 0, "min", -90)))));

        var result = mvc.get().uri("/api/robots/bittle-1/capabilities").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().isLenientlyEqualTo("""
                        {"schema": {"servos": [{"index": 0, "min": -90}]}}
                        """);
    }

    @Test
    void givenRegisteredRobot_whenServoStateRequested_thenItIsProxied() {
        when(robots.servoState("bittle-1")).thenReturn(new ServoState("bittle-1", true,
                "2026-08-30T12:00:00Z", List.of(new ServoJoint(0, 30))));

        var result = mvc.get().uri("/api/robots/bittle-1/servo").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.joints[0].angle").isEqualTo(30);
    }

    @Test
    void givenRegisteredRobot_whenServoMovePosted_thenItIsProxied() {
        when(robots.moveServos(eq("bittle-1"), any())).thenReturn(new ServoMoveResult("bittle-1",
                true, false, "Moved 1 joint(s)", List.of(new ServoJoint(0, 25))));

        var result = mvc.post().uri("/api/robots/bittle-1/servo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"joints\":[{\"index\":0,\"angle\":25}]}")
                .exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().isLenientlyEqualTo("""
                        {"success": true, "movedJoints": [{"index": 0}]}
                        """);
    }

    @Test
    void givenRegisteredRobot_whenPowerRequested_thenPassthroughPathIsRelayed() {
        when(passthrough.get("bittle-1", "/power")).thenReturn(Map.of("sessions", 2));

        var result = mvc.get().uri("/api/robots/bittle-1/power").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.sessions").isEqualTo(2);
    }

    @Test
    void givenUnknownGreetingAction_whenPosted_thenBadRequestWithoutTouchingTheAdapter() {
        var result = mvc.post().uri("/api/robots/bittle-1/greeting/explode").exchange();

        assertThat(result).hasStatus(HttpStatus.BAD_REQUEST)
                .bodyJson().extractingPath("$.error").isEqualTo("unknown_action");
        Mockito.verifyNoInteractions(passthrough);
    }

    @Test
    void givenUnknownRobot_whenStatusRequested_thenNotFoundIsReturned() {
        when(robots.status("ghost")).thenThrow(new RobotNotFoundException("ghost"));

        var result = mvc.get().uri("/api/robots/ghost/status").exchange();

        assertThat(result).hasStatus(HttpStatus.NOT_FOUND)
                .bodyJson().extractingPath("$.error").isEqualTo("robot_not_found");
    }

    @Test
    void givenAdapterDown_whenStatusRequested_thenBadGatewayAndFailureIsCounted() {
        when(robots.status("bittle-1"))
                .thenThrow(new AdapterUnavailableException("http://laika", null));

        var result = mvc.get().uri("/api/robots/bittle-1/status").exchange();

        assertThat(result).hasStatus(HttpStatus.BAD_GATEWAY)
                .bodyJson().extractingPath("$.error").isEqualTo("adapter_unavailable");
        Mockito.verify(metrics).recordAdapterUnavailable();
    }
}

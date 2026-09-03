package com.bittle.orchestrator.adapter.in.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
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
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.BinaryContent;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import com.bittle.orchestrator.domain.robot.ServoJoint;
import com.bittle.orchestrator.domain.robot.ServoMoveResult;
import com.bittle.orchestrator.domain.robot.ServoState;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

@WebMvcTest(RobotController.class)
@MockitoBean(types = {
        GetRobotStatusUseCase.class, GetRobotPersonalityUseCase.class, GetNextBehaviorUseCase.class,
        SendRobotCommandUseCase.class, InteractWithRobotUseCase.class, ListAnimationsUseCase.class,
        ExecuteAnimationUseCase.class, StartRobotAutonomousUseCase.class,
        StopRobotAutonomousUseCase.class, GetRobotAutonomousStatusUseCase.class,
        GetRobotActivityUseCase.class, GetRobotDisplayUseCase.class,
        GetRobotCapabilitiesUseCase.class, GetServoStateUseCase.class, MoveServosUseCase.class,
        RunVoiceDemoUseCase.class, GetVoiceHealthUseCase.class, PlaySoundUseCase.class,
        ExecuteRobotActionUseCase.class, RelayGetToRobotUseCase.class,
        RelayPostToRobotUseCase.class, RelayPostWithBodyToRobotUseCase.class,
        RelayGetBinaryFromRobotUseCase.class, OrchestratorMetricsPort.class})
class RobotControllerTest {

    private static final String SIT_DOWN_REQUEST =
            "{\"action\":\"sit_down\",\"durationMs\":1500,\"sequenceId\":1}";

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private GetRobotStatusUseCase getStatus;

    @Autowired
    private GetRobotCapabilitiesUseCase getCapabilities;

    @Autowired
    private GetServoStateUseCase getServoState;

    @Autowired
    private MoveServosUseCase moveServos;

    @Autowired
    private ExecuteRobotActionUseCase executeAction;

    @Autowired
    private RelayGetToRobotUseCase relayGet;

    @Autowired
    private RelayPostToRobotUseCase relayPost;

    @Autowired
    private RelayPostWithBodyToRobotUseCase relayPostWithBody;

    @Autowired
    private RelayGetBinaryFromRobotUseCase relayGetBinary;

    @Autowired
    private OrchestratorMetricsPort metrics;

    @Test
    void givenLoopStopped_whenExecuteActionPosted_thenItIsProxiedToTheAgent() {
        when(executeAction.execute(eq("bittle-1"), any()))
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
        when(executeAction.execute(eq("bittle-1"), any()))
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
        when(getStatus.execute("bittle-1"))
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
        when(getCapabilities.execute("bittle-1")).thenReturn(Map.of(
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
        when(getServoState.execute("bittle-1")).thenReturn(new ServoState("bittle-1", true,
                "2026-08-30T12:00:00Z", List.of(new ServoJoint(0, 30))));

        var result = mvc.get().uri("/api/robots/bittle-1/servo").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.joints[0].angle").isEqualTo(30);
    }

    @Test
    void givenRegisteredRobot_whenServoMovePosted_thenItIsProxied() {
        when(moveServos.execute(eq("bittle-1"), any())).thenReturn(new ServoMoveResult("bittle-1",
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
        when(relayGet.execute("bittle-1", "/power")).thenReturn(Map.of("sessions", 2));

        var result = mvc.get().uri("/api/robots/bittle-1/power").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.sessions").isEqualTo(2);
    }

    @Test
    void givenMapFilters_whenSamplesRequested_thenOnlyKnownFiltersAreRelayed() {
        when(relayGet.execute("bittle-1", "/senses/samples?since=1700000000&limit=50"))
                .thenReturn(Map.of("matched", 3));

        var result = mvc.get()
                .uri("/api/robots/bittle-1/senses/samples?since=1700000000&limit=50&bogus=1&every=")
                .exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.matched").isEqualTo(3);
    }

    @Test
    void givenNoFilters_whenSamplesRequested_thenBarePathIsRelayed() {
        when(relayGet.execute("bittle-1", "/senses/samples")).thenReturn(Map.of("total", 0));

        var result = mvc.get().uri("/api/robots/bittle-1/senses/samples").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.total").isEqualTo(0);
    }

    @Test
    void givenPoseReset_whenPostedWithoutBody_thenEmptyBodyIsRelayed() {
        when(relayPostWithBody.execute("bittle-1", "/senses/pose/reset", Map.of()))
                .thenReturn(Map.of("pose", Map.of("x", 0)));

        var result = mvc.post().uri("/api/robots/bittle-1/senses/pose/reset").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.pose.x").isEqualTo(0);
    }

    @Test
    void givenUnknownGreetingAction_whenPosted_thenBadRequestWithoutTouchingTheAdapter() {
        var result = mvc.post().uri("/api/robots/bittle-1/greeting/explode").exchange();

        assertThat(result).hasStatus(HttpStatus.BAD_REQUEST)
                .bodyJson().extractingPath("$.error").isEqualTo("unknown_action");
        verifyNoInteractions(relayPost);
    }

    @Test
    void givenUnknownRobot_whenStatusRequested_thenNotFoundIsReturned() {
        when(getStatus.execute("ghost")).thenThrow(new RobotNotFoundException("ghost"));

        var result = mvc.get().uri("/api/robots/ghost/status").exchange();

        assertThat(result).hasStatus(HttpStatus.NOT_FOUND)
                .bodyJson().extractingPath("$.error").isEqualTo("robot_not_found");
    }

    @Test
    void givenAdapterDown_whenStatusRequested_thenBadGatewayAndFailureIsCounted() {
        when(getStatus.execute("bittle-1"))
                .thenThrow(new AdapterUnavailableException("http://laika", null));

        var result = mvc.get().uri("/api/robots/bittle-1/status").exchange();

        assertThat(result).hasStatus(HttpStatus.BAD_GATEWAY)
                .bodyJson().extractingPath("$.error").isEqualTo("adapter_unavailable");
        verify(metrics).recordAdapterUnavailable();
    }

    @Test
    void givenCachedFrame_whenSnapRequested_thenJpegBytesAreRelayedUncached() {
        byte[] jpeg = {(byte) 0xFF, (byte) 0xD8, 1, 2, 3};
        when(relayGetBinary.execute("bittle-1", "/eyes/snap"))
                .thenReturn(new BinaryContent(jpeg, "image/jpeg"));

        var result = mvc.get().uri("/api/robots/bittle-1/eyes/snap").exchange();

        assertThat(result).hasStatusOk()
                .hasContentType(MediaType.IMAGE_JPEG)
                .hasHeader("Cache-Control", "no-store");
        assertThat(result.getResponse().getContentAsByteArray()).isEqualTo(jpeg);
    }

    @Test
    void givenFreshFlag_whenSnapRequested_thenAdapterIsAskedForANewFrame() {
        when(relayGetBinary.execute("bittle-1", "/eyes/snap?fresh=1"))
                .thenReturn(new BinaryContent(new byte[] {1}, "image/jpeg"));

        var result = mvc.get().uri("/api/robots/bittle-1/eyes/snap?fresh=1").exchange();

        assertThat(result).hasStatusOk();
        verify(relayGetBinary).execute("bittle-1", "/eyes/snap?fresh=1");
    }

    @Test
    void givenSoundPosted_whenRelayed_thenPlayPathAndBodyReachTheAdapter() {
        when(relayPostWithBody.execute(eq("bittle-1"), eq("/mouth/play"), any()))
                .thenReturn(Map.of("text", "sound:positive_bark"));

        var result = mvc.post().uri("/api/robots/bittle-1/mouth/play")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sound\":\"positive_bark\"}")
                .exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.text").isEqualTo("sound:positive_bark");
        verify(relayPostWithBody).execute("bittle-1", "/mouth/play", Map.of("sound", "positive_bark"));
    }

    @Test
    void givenMoodPosted_whenRelayed_thenBodyReachesTheAdapterUnchanged() {
        when(relayPostWithBody.execute(eq("bittle-1"), eq("/mood"), any()))
                .thenReturn(Map.of("mood", "happy"));

        var result = mvc.post().uri("/api/robots/bittle-1/mood")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"mood\":\"happy\",\"seconds\":3}")
                .exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.mood").isEqualTo("happy");
        verify(relayPostWithBody).execute("bittle-1", "/mood",
                Map.of("mood", "happy", "seconds", 3));
    }
}

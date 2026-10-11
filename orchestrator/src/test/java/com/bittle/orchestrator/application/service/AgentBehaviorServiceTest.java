package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AgentMetricsPort;
import com.bittle.orchestrator.application.port.out.ArbiterPort;
import com.bittle.orchestrator.application.port.out.BehaviorRunLogRepositoryPort;
import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class AgentBehaviorServiceTest {

    private static final Instant NOW = Instant.parse("2026-10-11T21:00:00Z");
    private static final UUID RUN = UUID.fromString("0f8fad5b-d9cb-469f-a165-70867728950e");
    private static final UUID DECISION = UUID.fromString("7c9e6679-7425-40de-944b-e07fc1f90ae7");

    private final ArbiterPort arbiter = mock(ArbiterPort.class);
    private final BehaviorRunLogRepositoryPort runLogs = mock(BehaviorRunLogRepositoryPort.class);
    private final SensorStateService sensors = mock(SensorStateService.class);
    private final RobotModeRepositoryPort modes = mock(RobotModeRepositoryPort.class);
    private final AgentMetricsPort metrics = mock(AgentMetricsPort.class);
    private final AgentBehaviorService service = new AgentBehaviorService(arbiter, runLogs,
            sensors, new GoalOutcomeEvaluator(List.of(), Clock.fixed(NOW, ZoneOffset.UTC)),
            mock(PatternRollupService.class), metrics, modes,
            Clock.fixed(NOW, ZoneOffset.UTC), 20, Duration.ofMinutes(10));

    @Test
    void givenToolCall_whenSubmitted_thenArbiterGetsAgentPriorityThreeWithDecisionInCause() {
        when(arbiter.submit(eq("bittle-1"), any()))
                .thenReturn(new ArbiterSubmissionResponse(RUN, "executing", null, 0));

        service.submitToolCall("bittle-1", "look_upward", "look_upward", DECISION);

        var request = ArgumentCaptor.forClass(ArbiterSubmissionRequest.class);
        verify(arbiter).submit(eq("bittle-1"), request.capture());
        assertThat(request.getValue().behaviorName()).isEqualTo("look_upward");
        assertThat(request.getValue().source()).isEqualTo("agent");
        assertThat(request.getValue().priority()).isEqualTo(3);
        assertThat(request.getValue().goal()).isEqualTo("look_upward");
        assertThat(request.getValue().cause())
                .containsEntry("type", "agent")
                .containsEntry("decisionId", DECISION.toString());
    }

    @Test
    void givenAcceptedSubmission_whenSubmitted_thenRunLogIsSavedUnderTheArbiterRunId() {
        var accepted = new ArbiterSubmissionResponse(RUN, "queued", null, 1);
        when(arbiter.submit(eq("bittle-1"), any())).thenReturn(accepted);

        var response = service.submitToolCall("bittle-1", "look_upward", "look_upward", DECISION);

        assertThat(response).isSameAs(accepted);
        var saved = ArgumentCaptor.forClass(BehaviorRunLog.class);
        verify(runLogs).save(saved.capture());
        BehaviorRunLog entry = saved.getValue();
        assertThat(entry.id()).isEqualTo(RUN);
        assertThat(entry.robotId()).isEqualTo("bittle-1");
        assertThat(entry.behaviorName()).isEqualTo("look_upward");
        assertThat(entry.source()).isEqualTo("agent");
        assertThat(entry.priority()).isEqualTo(3);
        assertThat(entry.goal()).isEqualTo("look_upward");
        assertThat(entry.cause())
                .containsEntry("type", "agent")
                .containsEntry("decisionId", DECISION.toString());
        assertThat(entry.timestamp()).isEqualTo(NOW);
        assertThat(entry.createdAt()).isEqualTo(NOW);
        assertThat(entry.completedAt()).isNull();
        assertThat(entry.hasOutcome()).isFalse();
    }

    @Test
    void givenToolCall_whenSubmitted_thenBeforeSnapshotIsCapturedBeforeTheArbiterIsCalled() {
        when(arbiter.submit(anyString(), any()))
                .thenReturn(new ArbiterSubmissionResponse(RUN, "executing", null, 0));

        service.submitToolCall("bittle-1", "look_upward", "look_upward", DECISION);

        var order = inOrder(sensors, arbiter);
        order.verify(sensors).captureSnapshot("bittle-1");
        order.verify(arbiter).submit(eq("bittle-1"), any());
    }

    @Test
    void givenRejectedSubmission_whenSubmitted_thenNothingIsSavedAndRejectionIsReturned() {
        when(arbiter.submit(anyString(), any()))
                .thenReturn(ArbiterSubmissionResponse.rejected("cooldown"));

        var response = service.submitToolCall("bittle-1", "look_upward", "look_upward", DECISION);

        assertThat(response.isAccepted()).isFalse();
        assertThat(response.message()).isEqualTo("cooldown");
        verify(runLogs, never()).save(any());
    }

    @Test
    void givenAcceptedWithoutRunId_whenSubmitted_thenResponseReturnedButNoEntrySaved() {
        when(arbiter.submit(anyString(), any()))
                .thenReturn(new ArbiterSubmissionResponse(null, "executing", null, 0));

        var response = service.submitToolCall("bittle-1", "look_upward", "look_upward", DECISION);

        assertThat(response.isAccepted()).isTrue();
        verify(runLogs, never()).save(any());
    }

    @Test
    void givenNoDecisionId_whenSubmitted_thenAFreshDecisionIdIsSent() {
        when(arbiter.submit(anyString(), any()))
                .thenReturn(new ArbiterSubmissionResponse(RUN, "executing", null, 0));

        service.submitToolCall("bittle-1", "bark", null, null);

        var request = ArgumentCaptor.forClass(ArbiterSubmissionRequest.class);
        verify(arbiter).submit(eq("bittle-1"), request.capture());
        assertThat(UUID.fromString(request.getValue().decisionId())).isNotNull();
        assertThat(request.getValue().goal()).isNull();
    }

    @Test
    void givenBlankToolName_whenSubmitted_thenRejectedWithoutCallingTheArbiter() {
        var response = service.submitToolCall("bittle-1", " ", "look_upward", DECISION);

        assertThat(response.isAccepted()).isFalse();
        verifyNoInteractions(arbiter, runLogs, sensors);
    }

    @Test
    void givenRepositoryFailure_whenSubmitted_thenTheAcceptedResponseIsStillReturned() {
        var accepted = new ArbiterSubmissionResponse(RUN, "executing", null, 0);
        when(arbiter.submit(anyString(), any())).thenReturn(accepted);
        when(runLogs.save(any())).thenThrow(new IllegalStateException("db down"));

        assertThat(service.submitToolCall("bittle-1", "look_upward", "look_upward", DECISION))
                .isSameAs(accepted);
    }

    // ---- AGENT-16: mode constraints -------------------------------------------

    @Test
    void givenStationaryRobot_whenWalkingToolSubmitted_thenRejectedBeforeTheArbiter() {
        when(modes.find("bittle-1")).thenReturn(Optional.of(
                new RobotMode("bittle-1", OperatingMode.STATIONARY, NOW, "gui")));

        var response = service.submitToolCall("bittle-1", "move_forward", "move_forward",
                DECISION);

        assertThat(response.isAccepted()).isFalse();
        assertThat(response.message())
                .startsWith("Tool 'move_forward' is not available in stationary mode")
                .contains("look_upward");
        verifyNoInteractions(arbiter, runLogs, sensors);
    }

    @Test
    void givenRoamingRobot_whenWalkingToolSubmitted_thenItGoesToTheArbiter() {
        when(modes.find("bittle-1")).thenReturn(Optional.of(
                new RobotMode("bittle-1", OperatingMode.ROAMING, NOW, "gui")));
        when(arbiter.submit(anyString(), any()))
                .thenReturn(new ArbiterSubmissionResponse(RUN, "executing", null, 0));

        var response = service.submitToolCall("bittle-1", "move_forward", "move_forward",
                DECISION);

        assertThat(response.isAccepted()).isTrue();
        verify(arbiter).submit(eq("bittle-1"), any());
    }

    @Test
    void givenFruitflyRobot_whenAnyToolSubmitted_thenRejectedWithNoToolsMessage() {
        when(modes.find("bittle-1")).thenReturn(Optional.of(
                new RobotMode("bittle-1", OperatingMode.FRUITFLY, NOW, "gui")));

        var response = service.submitToolCall("bittle-1", "bark", null, DECISION);

        assertThat(response.status()).isEqualTo(ArbiterSubmissionResponse.REJECTED);
        assertThat(response.message()).contains("fruitfly").contains("no agent tools");
        verifyNoInteractions(arbiter);
    }

    @Test
    void givenNoStoredMode_whenToolSubmitted_thenStationaryRulesApply() {
        when(modes.find("bittle-1")).thenReturn(Optional.empty());

        assertThat(service.submitToolCall("bittle-1", "turn_left", null, DECISION).isAccepted())
                .isFalse();
        verifyNoInteractions(arbiter);
    }

    @Test
    void givenUnknownTool_whenSubmitted_thenRejected() {
        var response = service.submitToolCall("bittle-1", "backflip", null, DECISION);

        assertThat(response.message()).contains("backflip");
        verifyNoInteractions(arbiter);
    }

    @Test
    void givenModeUnreadable_whenToolSubmitted_thenRefused() {
        when(modes.find("bittle-1")).thenThrow(new IllegalStateException("db down"));

        var response = service.submitToolCall("bittle-1", "bark", null, DECISION);

        assertThat(response.isAccepted()).isFalse();
        assertThat(response.message()).contains("Operating mode unavailable");
        verifyNoInteractions(arbiter);
    }

    // ---- AGENT-18: submission metrics -------------------------------------------

    @Test
    void givenSubmissions_whenAnswered_thenEachResultIsCountedPerTool() {
        when(arbiter.submit(anyString(), any()))
                .thenReturn(new ArbiterSubmissionResponse(RUN, "executing", null, 0))
                .thenReturn(ArbiterSubmissionResponse.rejected("cooldown"));

        service.submitToolCall("bittle-1", "bark", null, DECISION);
        service.submitToolCall("bittle-1", "bark", null, DECISION);
        service.submitToolCall("bittle-1", "move_forward", null, DECISION);
        service.submitToolCall("bittle-1", "backflip", null, DECISION);

        verify(metrics).recordSubmission("bark", "accepted");
        verify(metrics).recordSubmission("bark", "rejected");
        verify(metrics).recordSubmission("move_forward", "mode_rejected");
        verify(metrics).recordSubmission("other", "mode_rejected");
    }
}

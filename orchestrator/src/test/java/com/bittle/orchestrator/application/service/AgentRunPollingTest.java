package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AgentMetricsPort;
import com.bittle.orchestrator.application.port.out.ArbiterPort;
import com.bittle.orchestrator.application.port.out.BehaviorRunLogRepositoryPort;
import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.bittle.orchestrator.domain.behavior.outcome.GoalCheck;
import com.bittle.orchestrator.domain.behavior.outcome.GoalOutcomeChecker;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class AgentRunPollingTest {

    private static final Instant STARTED = Instant.parse("2026-10-11T21:00:00Z");
    private static final Instant NOW = STARTED.plusSeconds(5);
    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);

    private final ArbiterPort arbiter = mock(ArbiterPort.class);
    private final BehaviorRunLogRepositoryPort runLogs = mock(BehaviorRunLogRepositoryPort.class);
    private final SensorStateService sensors = mock(SensorStateService.class);
    private final GoalOutcomeChecker moveForward = new GoalOutcomeChecker() {
        @Override
        public String goal() {
            return "move_forward";
        }

        @Override
        public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
            double moved = after.odometryPosition().xCm() - before.odometryPosition().xCm();
            return moved >= 5 ? GoalCheck.succeeded(0.6, "moved " + moved)
                    : GoalCheck.failed(0.9, "moved " + moved);
        }
    };
    private final PatternRollupService rollups = mock(PatternRollupService.class);
    private final AgentMetricsPort metrics = mock(AgentMetricsPort.class);
    private final AgentBehaviorService service = new AgentBehaviorService(arbiter, runLogs,
            sensors, new GoalOutcomeEvaluator(List.of(moveForward), CLOCK), rollups, metrics,
            mock(RobotModeRepositoryPort.class), CLOCK, 20, Duration.ofMinutes(10));

    @Test
    void givenFinishedRun_whenPolled_thenOutcomeIsEvaluatedSavedAndSynced() {
        var entry = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id()))
                .thenReturn(Optional.of(remote(entry, STARTED.plusSeconds(3), null)));
        when(sensors.getSnapshotAt("bittle-1", STARTED)).thenReturn(Optional.of(at(0)));
        when(sensors.captureSnapshot("bittle-1")).thenReturn(at(12));
        when(arbiter.syncOutcome(eq("bittle-1"), eq(entry.id()), any())).thenReturn(true);

        int closed = service.pollAndEvaluateCompletions();

        assertThat(closed).isEqualTo(1);
        var saved = ArgumentCaptor.forClass(BehaviorRunLog.class);
        verify(runLogs).save(saved.capture());
        var run = saved.getValue();
        assertThat(run.id()).isEqualTo(entry.id());
        assertThat(run.completedAt()).isEqualTo(STARTED.plusSeconds(3));
        assertThat(run.executionTimeMs()).isEqualTo(3000L);
        assertThat(run.updatedAt()).isEqualTo(NOW);
        assertThat(run.goal()).isEqualTo("move_forward");
        assertThat(run.outcome().success()).isTrue();
        assertThat(run.outcome().reason()).isEqualTo("moved 12.0");
        assertThat(run.outcome().evaluatedAt()).isEqualTo(NOW);
        verify(arbiter).syncOutcome("bittle-1", entry.id(), run.outcome());
    }

    @Test
    void givenRunStillRunning_whenPolled_thenNothingIsSaved() {
        var entry = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id()))
                .thenReturn(Optional.of(remote(entry, null, null)));

        assertThat(service.pollAndEvaluateCompletions()).isZero();
        verify(runLogs, never()).save(any());
        verify(sensors, never()).captureSnapshot(any());
    }

    @Test
    void givenQueuedRunUnknownToAdapterYet_whenPolled_thenItStaysPending() {
        var entry = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id())).thenReturn(Optional.empty());

        assertThat(service.pollAndEvaluateCompletions()).isZero();
        verify(runLogs, never()).save(any());
    }

    @Test
    void givenPreemptedRun_whenPolled_thenOutcomeIsUndeterminedWithoutEvaluation() {
        var entry = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id()))
                .thenReturn(Optional.of(remote(entry, STARTED.plusSeconds(1), "other-run")));

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        var saved = ArgumentCaptor.forClass(BehaviorRunLog.class);
        verify(runLogs).save(saved.capture());
        assertThat(saved.getValue().outcome().success()).isNull();
        assertThat(saved.getValue().outcome().reason()).contains("preempted by other-run");
        assertThat(saved.getValue().preemptedBy()).isEqualTo("other-run");
        verify(sensors, never()).captureSnapshot(any());
    }

    @Test
    void givenRunWithoutBeforeSnapshot_whenPolled_thenUndeterminedOutcomeIsStillSaved() {
        var entry = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id()))
                .thenReturn(Optional.of(remote(entry, STARTED.plusSeconds(3), null)));
        when(sensors.getSnapshotAt("bittle-1", STARTED)).thenReturn(Optional.empty());
        when(sensors.captureSnapshot("bittle-1")).thenReturn(at(12));

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        var saved = ArgumentCaptor.forClass(BehaviorRunLog.class);
        verify(runLogs).save(saved.capture());
        assertThat(saved.getValue().outcome().success()).isNull();
        assertThat(saved.getValue().completedAt()).isNotNull();
    }

    @Test
    void givenStaleRun_whenPolled_thenItIsClosedAsUndetermined() {
        var entry = pending("move_forward", NOW.minus(Duration.ofMinutes(11)));
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id())).thenReturn(Optional.empty());

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        var saved = ArgumentCaptor.forClass(BehaviorRunLog.class);
        verify(runLogs).save(saved.capture());
        assertThat(saved.getValue().completedAt()).isEqualTo(NOW);
        assertThat(saved.getValue().outcome().success()).isNull();
        assertThat(saved.getValue().outcome().reason()).contains("unknown to the adapter");
    }

    @Test
    void givenOneRunFails_whenPolled_thenTheOthersAreStillProcessed() {
        var broken = pending("move_forward", STARTED);
        var fine = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(broken, fine));
        when(arbiter.getRunLog("bittle-1", broken.id()))
                .thenThrow(new IllegalStateException("boom"));
        when(arbiter.getRunLog("bittle-1", fine.id()))
                .thenReturn(Optional.of(remote(fine, STARTED.plusSeconds(3), null)));
        when(sensors.getSnapshotAt("bittle-1", STARTED)).thenReturn(Optional.of(at(0)));
        when(sensors.captureSnapshot("bittle-1")).thenReturn(at(1));

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        verify(runLogs, times(1)).save(any());
    }

    @Test
    void givenSyncFails_whenPolled_thenTheOutcomeIsStillSaved() {
        var entry = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id()))
                .thenReturn(Optional.of(remote(entry, STARTED.plusSeconds(3), null)));
        when(sensors.getSnapshotAt("bittle-1", STARTED)).thenReturn(Optional.of(at(0)));
        when(sensors.captureSnapshot("bittle-1")).thenReturn(at(12));
        when(arbiter.syncOutcome(any(), any(), any())).thenReturn(false);

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        verify(runLogs).save(any());
    }

    @Test
    void givenRepositoryDown_whenPolled_thenZeroAndNoException() {
        when(runLogs.findPendingBySource(any(), anyInt()))
                .thenThrow(new IllegalStateException("db down"));

        assertThat(service.pollAndEvaluateCompletions()).isZero();
    }

    @Test
    void givenFinishedRun_whenPolled_thenPatternsAreRolledUpAfterTheOutcomeIsSaved() {
        var entry = finishedRun();
        when(rollups.rollupPatternsForGoal("bittle-1", "move_forward"))
                .thenReturn(List.of(LearnedPattern.discovered("bittle-1", "move_forward",
                        List.of("walk_forward"), NOW)));

        service.pollAndEvaluateCompletions();

        var order = inOrder(runLogs, rollups);
        order.verify(runLogs).save(any());
        order.verify(rollups).rollupPatternsForGoal("bittle-1", "move_forward");
        verify(metrics).recordOutcome("move_forward", true);
        verify(metrics).recordRollup(eq("move_forward"), eq(1), anyLong());
    }

    @Test
    void givenRollupFails_whenPolled_thenTheRunStillCountsAndTheFailureIsRecorded() {
        finishedRun();
        when(rollups.rollupPatternsForGoal(any(), any()))
                .thenThrow(new IllegalStateException("db down"));

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        verify(metrics).recordRollupFailure("move_forward");
        verify(metrics, never()).recordRollup(any(), anyInt(), anyLong());
    }

    @Test
    void givenMetricsFail_whenPolled_thenPollingContinues() {
        finishedRun();
        org.mockito.Mockito.doThrow(new IllegalStateException("registry"))
                .when(metrics).recordOutcome(any(), any());

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        verify(rollups).rollupPatternsForGoal("bittle-1", "move_forward");
    }

    @Test
    void givenRunWithoutGoal_whenPolled_thenNoRollupButOutcomeMetric() {
        var entry = pending(null, STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id()))
                .thenReturn(Optional.of(remote(entry, STARTED.plusSeconds(3), null)));
        when(sensors.captureSnapshot("bittle-1")).thenReturn(at(1));
        when(sensors.getSnapshotAt("bittle-1", STARTED)).thenReturn(Optional.of(at(0)));

        assertThat(service.pollAndEvaluateCompletions()).isEqualTo(1);
        verifyNoInteractions(rollups);
        verify(metrics).recordOutcome(null, null);
    }

    @Test
    void givenStaleRun_whenClosed_thenPatternsAreRolledUpToo() {
        var entry = pending("move_forward", NOW.minus(Duration.ofMinutes(11)));
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id())).thenReturn(Optional.empty());

        service.pollAndEvaluateCompletions();

        verify(rollups).rollupPatternsForGoal("bittle-1", "move_forward");
        verify(metrics).recordOutcome("move_forward", null);
    }

    private BehaviorRunLog finishedRun() {
        var entry = pending("move_forward", STARTED);
        when(runLogs.findPendingBySource("agent", 20)).thenReturn(List.of(entry));
        when(arbiter.getRunLog("bittle-1", entry.id()))
                .thenReturn(Optional.of(remote(entry, STARTED.plusSeconds(3), null)));
        when(sensors.getSnapshotAt("bittle-1", STARTED)).thenReturn(Optional.of(at(0)));
        when(sensors.captureSnapshot("bittle-1")).thenReturn(at(12));
        when(arbiter.syncOutcome(any(), any(), any())).thenReturn(true);
        return entry;
    }

    private static BehaviorRunLog pending(String goal, Instant startedAt) {
        return new BehaviorRunLog(UUID.randomUUID(), "bittle-1", startedAt, null, "walk_forward",
                "agent", 3, Map.of("type", "agent", "decisionId", "d-1"), null, null, goal, null,
                null, startedAt, startedAt);
    }

    private static BehaviorRunLog remote(BehaviorRunLog entry, Instant completedAt,
                                         String preemptedBy) {
        Long ms = completedAt == null ? null
                : Duration.between(entry.timestamp(), completedAt).toMillis();
        return new BehaviorRunLog(entry.id(), entry.robotId(), entry.timestamp(), completedAt,
                entry.behaviorName(), "agent", 3, entry.cause(), ms, preemptedBy, entry.goal(),
                (OutcomeEvaluation) null, null, entry.timestamp(), completedAt);
    }

    private static SensorSnapshot at(double xCm) {
        return new SensorSnapshot(NOW, null, new SensorSnapshot.Odometry(xCm, 0, 0), null, null);
    }
}

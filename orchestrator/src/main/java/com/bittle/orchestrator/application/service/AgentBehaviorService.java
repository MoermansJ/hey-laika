package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.out.AgentMetricsPort;
import com.bittle.orchestrator.application.port.out.ArbiterPort;
import com.bittle.orchestrator.application.port.out.BehaviorRunLogRepositoryPort;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Agent tool-call lifecycle in the orchestrator (AGENT_TOOL_COMPOSITION_DESIGN.md §3.3).
 * <ul>
 *   <li>Submission (AGENT-05): a tool call from Claude goes to the robot's arbiter at
 *       priority 3 with agent provenance; an accepted run gets a local run-log entry under
 *       the arbiter's run id, and a "before" sensor snapshot is captured.</li>
 *   <li>Completion (AGENT-10): {@link #pollAndEvaluateCompletions()} asks the arbiter
 *       about pending agent runs; a finished run gets an "after" snapshot, an outcome
 *       from the {@link GoalOutcomeEvaluator}, an updated run-log entry and the outcome
 *       synced back to the adapter.</li>
 *   <li>Learning (AGENT-12): each saved outcome triggers the goal's pattern rollup and
 *       agent metrics.</li>
 * </ul>
 */
public class AgentBehaviorService {

    private static final Logger log = LoggerFactory.getLogger(AgentBehaviorService.class);
    /** Rollups slower than this are logged (design target: under 2 ms per goal). */
    private static final long SLOW_ROLLUP_NANOS = 50_000_000L;

    private final ArbiterPort arbiter;
    private final BehaviorRunLogRepositoryPort runLogs;
    private final SensorStateService sensors;
    private final GoalOutcomeEvaluator evaluator;
    private final PatternRollupService rollups;
    private final AgentMetricsPort metrics;
    private final Clock clock;
    private final int pollBatchSize;
    private final Duration staleAfter;

    public AgentBehaviorService(ArbiterPort arbiter, BehaviorRunLogRepositoryPort runLogs,
                                SensorStateService sensors, GoalOutcomeEvaluator evaluator,
                                PatternRollupService rollups, AgentMetricsPort metrics,
                                Clock clock, int pollBatchSize, Duration staleAfter) {
        this.arbiter = Objects.requireNonNull(arbiter, "arbiter");
        this.runLogs = Objects.requireNonNull(runLogs, "runLogs");
        this.sensors = Objects.requireNonNull(sensors, "sensors");
        this.evaluator = Objects.requireNonNull(evaluator, "evaluator");
        this.rollups = Objects.requireNonNull(rollups, "rollups");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.staleAfter = Objects.requireNonNull(staleAfter, "staleAfter");
        if (pollBatchSize <= 0) {
            throw new IllegalArgumentException("pollBatchSize must be positive: " + pollBatchSize);
        }
        this.pollBatchSize = pollBatchSize;
    }

    /**
     * Submit an agent-sourced tool call to the arbiter.
     *
     * @param robotId      robot to act
     * @param toolName     named behavior to run
     * @param declaredGoal goal the agent wants the tool call to achieve (may be null)
     * @param decisionId   the agent decision this call belongs to; a fresh id is used when null
     * @return the arbiter's answer; a rejection when the adapter refused or was unreachable
     */
    public ArbiterSubmissionResponse submitToolCall(String robotId, String toolName,
                                                    String declaredGoal, UUID decisionId) {
        Objects.requireNonNull(robotId, "robotId");
        if (toolName == null || toolName.isBlank()) {
            return ArbiterSubmissionResponse.rejected("toolName is required");
        }
        UUID decision = decisionId != null ? decisionId : UUID.randomUUID();
        var request = ArbiterSubmissionRequest.forAgent(toolName, declaredGoal,
                decision.toString());

        // The "before" state must be read before the arbiter can start moving.
        captureQuietly(robotId);
        ArbiterSubmissionResponse response = arbiter.submit(robotId, request);
        if (response == null) {
            return ArbiterSubmissionResponse.rejected("Empty arbiter response");
        }
        if (!response.isAccepted()) {
            log.info("Agent tool call {} for {} (goal {}) rejected: {}", toolName, robotId,
                    declaredGoal, response.message());
            return response;
        }
        if (response.runLogId() == null) {
            // Without the arbiter's run id the entry could never be matched when polling.
            log.warn("Agent tool call {} for {} accepted ({}) without a run id; no run-log entry",
                    toolName, robotId, response.status());
            return response;
        }
        record(robotId, request, response.runLogId());
        log.info("Agent tool call {} for {} (goal {}, decision {}) -> {} run {}", toolName,
                robotId, declaredGoal, decision, response.status(), response.runLogId());
        return response;
    }

    /**
     * One polling pass over pending agent runs (oldest first, at most the batch size).
     * A run the arbiter reports as finished is evaluated and saved; a run with no
     * completion after the stale timeout is closed as undetermined so it stops being
     * polled. Failures on one run are logged and do not stop the others.
     *
     * @return how many runs were closed in this pass
     */
    public int pollAndEvaluateCompletions() {
        List<BehaviorRunLog> pending;
        try {
            pending = runLogs.findPendingBySource(ArbiterSubmissionRequest.SOURCE_AGENT,
                    pollBatchSize);
        } catch (RuntimeException e) {
            log.warn("Could not load pending agent runs: {}", e.getMessage());
            return 0;
        }
        int closed = 0;
        for (BehaviorRunLog entry : pending) {
            try {
                if (pollOne(entry)) {
                    closed++;
                }
            } catch (RuntimeException e) {
                log.warn("Evaluating agent run {} for {} failed: {}", entry.id(),
                        entry.robotId(), e.toString());
            }
        }
        return closed;
    }

    private boolean pollOne(BehaviorRunLog entry) {
        Instant now = clock.instant();
        Optional<BehaviorRunLog> remote = arbiter.getRunLog(entry.robotId(), entry.id());
        Instant completedAt = remote.map(BehaviorRunLog::completedAt).orElse(null);
        if (completedAt == null) {
            if (Duration.between(entry.timestamp(), now).compareTo(staleAfter) > 0) {
                closeStale(entry, now, remote.isPresent());
                return true;
            }
            return false;
        }
        BehaviorRunLog finished = remote.get();
        OutcomeEvaluation outcome;
        if (finished.preemptedBy() != null) {
            outcome = undetermined("Run did not finish: preempted by " + finished.preemptedBy(),
                    now);
        } else {
            SensorSnapshot before = sensors.getSnapshotAt(entry.robotId(), entry.timestamp())
                    .orElse(null);
            SensorSnapshot after = sensors.captureSnapshot(entry.robotId());
            outcome = evaluator.evaluateOutcome(entry, before, after);
        }
        var updated = new BehaviorRunLog(entry.id(), entry.robotId(), entry.timestamp(),
                completedAt, entry.behaviorName(), entry.source(), entry.priority(),
                entry.cause(), finished.executionTimeMs(), finished.preemptedBy(), entry.goal(),
                outcome, entry.sensorDelta(), entry.createdAt(), now);
        runLogs.save(updated);
        if (!arbiter.syncOutcome(entry.robotId(), entry.id(), outcome)) {
            log.warn("Outcome of run {} saved but not synced to the adapter", entry.id());
        }
        log.info("Agent run {} ({} for goal {}) finished: success={} confidence={} ({})",
                entry.id(), entry.behaviorName(), entry.goal(), outcome.success(),
                outcome.confidence(), outcome.reason());
        afterOutcomeSaved(entry, outcome);
        return true;
    }

    private void closeStale(BehaviorRunLog entry, Instant now, boolean adapterKnowsRun) {
        String reason = adapterKnowsRun
                ? "No completion reported within " + staleAfter.toMinutes() + " min"
                : "Run unknown to the adapter after " + staleAfter.toMinutes() + " min";
        var outcome = undetermined(reason, now);
        runLogs.save(new BehaviorRunLog(entry.id(), entry.robotId(), entry.timestamp(), now,
                entry.behaviorName(), entry.source(), entry.priority(), entry.cause(), null,
                entry.preemptedBy(), entry.goal(), outcome, entry.sensorDelta(),
                entry.createdAt(), now));
        log.warn("Agent run {} for {} closed as stale: {}", entry.id(), entry.robotId(), reason);
        afterOutcomeSaved(entry, outcome);
    }

    /**
     * Every outcome write refreshes the goal's learned patterns right away (design §3.4:
     * rollup on write, not periodic). A failing rollup is logged and counted; it never
     * stops the polling pass.
     */
    private void afterOutcomeSaved(BehaviorRunLog entry, OutcomeEvaluation outcome) {
        recordQuietly(() -> metrics.recordOutcome(entry.goal(), outcome.success()));
        if (entry.goal() == null || entry.goal().isBlank()) {
            return;
        }
        long started = System.nanoTime();
        try {
            int active = rollups.rollupPatternsForGoal(entry.robotId(), entry.goal()).size();
            long elapsed = System.nanoTime() - started;
            recordQuietly(() -> metrics.recordRollup(entry.goal(), active, elapsed));
            if (elapsed > SLOW_ROLLUP_NANOS) {
                log.warn("Pattern rollup for {} goal {} took {} ms", entry.robotId(),
                        entry.goal(), elapsed / 1_000_000);
            }
        } catch (RuntimeException e) {
            log.warn("Pattern rollup for {} goal {} failed after run {}: {}", entry.robotId(),
                    entry.goal(), entry.id(), e.toString());
            recordQuietly(() -> metrics.recordRollupFailure(entry.goal()));
        }
    }

    private static void recordQuietly(Runnable record) {
        try {
            record.run();
        } catch (RuntimeException e) {
            log.debug("Agent metric not recorded: {}", e.getMessage());
        }
    }

    private static OutcomeEvaluation undetermined(String reason, Instant now) {
        return new OutcomeEvaluation(null, 0.0, reason, GoalOutcomeEvaluator.EVALUATOR_VERSION,
                now);
    }

    private void captureQuietly(String robotId) {
        try {
            sensors.captureSnapshot(robotId);
        } catch (RuntimeException e) {
            log.debug("Before-snapshot for {} failed: {}", robotId, e.getMessage());
        }
    }

    private void record(String robotId, ArbiterSubmissionRequest request, UUID runLogId) {
        Instant now = clock.instant();
        var entry = new BehaviorRunLog(runLogId, robotId, now, null, request.behaviorName(),
                request.source(), request.priority(), request.cause(), null, null,
                request.goal(), null, null, now, now);
        try {
            runLogs.save(entry);
        } catch (RuntimeException e) {
            // The arbiter already accepted the run; the robot moves either way.
            log.error("Could not store run-log entry {} for {}: {}", runLogId, robotId,
                    e.getMessage(), e);
        }
    }
}

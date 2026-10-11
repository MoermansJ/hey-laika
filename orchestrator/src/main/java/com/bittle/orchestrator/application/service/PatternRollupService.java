package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.out.BehaviorRunLogRepositoryPort;
import com.bittle.orchestrator.application.port.out.LearnedPatternRepositoryPort;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.PatternStatus;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Mines learned patterns from run-log outcomes (AGENT_TOOL_COMPOSITION_DESIGN.md §3.4,
 * AGENT-11): for one robot and goal, recompute attempts, successes and success rate of
 * every tool combination the agent has tried, and store them as {@link LearnedPattern}s.
 *
 * <p><b>Tool combination.</b> The agent may call several tools for one decision; the
 * runs of one decision share {@code cause.decisionId}. A combination is the ordered
 * (by start time) list of tool names of one decision's evaluated runs; a run without a
 * decision id is a combination of its own. One decision is one attempt.
 *
 * <p><b>Success.</b> An attempt counts as a success when the outcome of its last run
 * (the state the robot ended in) is {@code success = true}, and as a failure when it is
 * {@code false}. Attempts whose last outcome is undetermined ({@code success = null}:
 * no checker, missing sensor data, preempted, stale) are left out of the statistics.
 *
 * <p>A stored pattern whose combination no longer appears (e.g. a decision that later
 * gained another tool) is reset to zero counts and marked {@link PatternStatus#INACTIVE}.
 */
public class PatternRollupService {

    private static final Logger log = LoggerFactory.getLogger(PatternRollupService.class);

    private final BehaviorRunLogRepositoryPort runLogs;
    private final LearnedPatternRepositoryPort patterns;
    private final Clock clock;

    public PatternRollupService(BehaviorRunLogRepositoryPort runLogs,
                                LearnedPatternRepositoryPort patterns, Clock clock) {
        this.runLogs = Objects.requireNonNull(runLogs, "runLogs");
        this.patterns = Objects.requireNonNull(patterns, "patterns");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    /**
     * Recompute and save all patterns for the goal.
     *
     * @return the active patterns after the rollup, highest success rate first
     */
    public List<LearnedPattern> rollupPatternsForGoal(String robotId, String goal) {
        Objects.requireNonNull(robotId, "robotId");
        if (goal == null || goal.isBlank()) {
            return List.of();
        }
        long started = System.nanoTime();
        Instant now = clock.instant();

        Map<List<String>, Stats> byCombination = new LinkedHashMap<>();
        for (List<BehaviorRunLog> attempt : attempts(robotId, goal)) {
            BehaviorRunLog last = attempt.get(attempt.size() - 1);
            Boolean success = last.outcome().success();
            if (success == null) {
                continue;
            }
            List<String> combination = attempt.stream().map(BehaviorRunLog::behaviorName).toList();
            byCombination.computeIfAbsent(combination, c -> new Stats())
                    .add(success, attempt.get(0).timestamp());
        }

        Map<List<String>, LearnedPattern> existing = new HashMap<>();
        for (LearnedPattern pattern : patterns.findByRobotIdAndGoal(robotId, goal)) {
            existing.put(pattern.toolCombination(), pattern);
        }

        List<LearnedPattern> active = new ArrayList<>();
        for (var entry : byCombination.entrySet()) {
            Stats stats = entry.getValue();
            LearnedPattern base = existing.remove(entry.getKey());
            if (base == null) {
                base = LearnedPattern.discovered(robotId, goal, entry.getKey(), now);
            }
            active.add(patterns.save(base.withStats(stats.attempts, stats.successes,
                    stats.lastUsed, now)));
        }
        for (LearnedPattern stale : existing.values()) {
            if (stale.attempts() != 0 || stale.status() != PatternStatus.INACTIVE) {
                patterns.save(new LearnedPattern(stale.id(), robotId, goal,
                        stale.toolCombination(), 0, 0, 0.0, stale.firstDiscovered(),
                        stale.lastUsed(), PatternStatus.INACTIVE, stale.createdAt(), now));
            }
        }

        active.sort(Comparator.comparingDouble(LearnedPattern::successRate).reversed()
                .thenComparing(Comparator.comparingInt(LearnedPattern::attempts).reversed()));
        double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;
        log.info("Pattern rollup {} goal {}: {} active pattern(s){}, {} retired in {} ms",
                robotId, goal, active.size(), best(active), existing.size(),
                String.format(Locale.ROOT, "%.2f", elapsedMs));
        return List.copyOf(active);
    }

    /** Evaluated agent runs for the goal, grouped per decision, each group in start order. */
    private List<List<BehaviorRunLog>> attempts(String robotId, String goal) {
        Map<String, List<BehaviorRunLog>> byDecision = new LinkedHashMap<>();
        runLogs.findByRobotIdAndGoalWithOutcome(robotId, goal).stream()
                .filter(run -> ArbiterSubmissionRequest.SOURCE_AGENT.equals(run.source()))
                .filter(run -> run.behaviorName() != null && run.outcome() != null)
                .sorted(Comparator.comparing(BehaviorRunLog::timestamp))
                .forEach(run -> byDecision.computeIfAbsent(decisionKey(run),
                        k -> new ArrayList<>()).add(run));
        return new ArrayList<>(byDecision.values());
    }

    private static String decisionKey(BehaviorRunLog run) {
        Object decision = run.cause() == null ? null : run.cause().get("decisionId");
        return decision != null ? "decision:" + decision : "run:" + run.id();
    }

    private static String best(List<LearnedPattern> active) {
        if (active.isEmpty()) {
            return "";
        }
        LearnedPattern top = active.get(0);
        return String.format(Locale.ROOT, ", best %s at %.2f over %d",
                top.toolCombination(), top.successRate(), top.attempts());
    }

    private static final class Stats {
        private int attempts;
        private int successes;
        private Instant lastUsed;

        void add(boolean success, Instant at) {
            attempts++;
            if (success) {
                successes++;
            }
            if (lastUsed == null || at.isAfter(lastUsed)) {
                lastUsed = at;
            }
        }
    }
}

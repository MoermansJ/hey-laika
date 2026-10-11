package com.bittle.orchestrator.domain.behavior;

import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Aggregated success statistics for one ordered tool combination tried towards
 * one goal on one robot (AGENT_TOOL_COMPOSITION_DESIGN.md §2.2). Patterns are
 * fleet-local: they are keyed by {@code (robotId, goal, toolCombination)} and
 * recomputed from run-log outcomes by the rollup service.
 *
 * <p>The design sketches a mutable bean with a transient {@code isDirty} flag;
 * this follows the codebase's immutable-record style instead, so "dirty"
 * tracking is unnecessary (a changed pattern is simply a new value to save).
 */
public record LearnedPattern(UUID id, String robotId, String goal, List<String> toolCombination,
                             int attempts, int successes, double successRate,
                             Instant firstDiscovered, Instant lastUsed, PatternStatus status,
                             Instant createdAt, Instant updatedAt) {

    public LearnedPattern {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(robotId, "robotId");
        Objects.requireNonNull(goal, "goal");
        Objects.requireNonNull(toolCombination, "toolCombination");
        Objects.requireNonNull(status, "status");
        if (toolCombination.isEmpty()) {
            throw new IllegalArgumentException("toolCombination must not be empty");
        }
        if (attempts < 0 || successes < 0 || successes > attempts) {
            throw new IllegalArgumentException(
                    "invalid counts: attempts=" + attempts + ", successes=" + successes);
        }
        toolCombination = List.copyOf(toolCombination);
    }

    /** A new, never-attempted pattern for the given combination. */
    public static LearnedPattern discovered(String robotId, String goal, List<String> toolCombination,
                                            Instant now) {
        return new LearnedPattern(UUID.randomUUID(), robotId, goal, toolCombination, 0, 0, 0.0,
                now, null, PatternStatus.ACTIVE, now, now);
    }

    /** {@code successes / attempts}, or 0 when nothing has been attempted. */
    public static double rate(int attempts, int successes) {
        return attempts == 0 ? 0.0 : (double) successes / attempts;
    }

    /** Copy with recomputed statistics (success rate derived), status active. */
    public LearnedPattern withStats(int newAttempts, int newSuccesses, Instant newLastUsed,
                                    Instant now) {
        return new LearnedPattern(id, robotId, goal, toolCombination, newAttempts, newSuccesses,
                rate(newAttempts, newSuccesses), firstDiscovered, newLastUsed,
                PatternStatus.ACTIVE, createdAt, now);
    }

    /** Copy with a new status. */
    public LearnedPattern withStatus(PatternStatus newStatus, Instant now) {
        return new LearnedPattern(id, robotId, goal, toolCombination, attempts, successes,
                successRate, firstDiscovered, lastUsed, newStatus, createdAt, now);
    }
}

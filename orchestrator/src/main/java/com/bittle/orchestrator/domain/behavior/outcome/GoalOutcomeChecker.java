package com.bittle.orchestrator.domain.behavior.outcome;

/**
 * Judges whether a run achieved one goal by comparing the sensor state before
 * and after it (AGENT_TOOL_COMPOSITION_DESIGN.md §3.2). One implementation per
 * goal; the {@code GoalOutcomeEvaluator} picks it by {@link #goal()}.
 */
public interface GoalOutcomeChecker {

    /** The declared goal this checker evaluates, e.g. "look_upward". */
    String goal();

    /**
     * Compare the snapshots. Both are non-null, but any reading inside them may be
     * null; return {@link GoalCheck#undetermined(String)} when the needed data is missing.
     */
    GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after);
}

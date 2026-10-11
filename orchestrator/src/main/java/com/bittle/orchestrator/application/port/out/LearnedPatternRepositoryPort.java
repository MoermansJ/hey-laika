package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.PatternStatus;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Persistence for the learned-patterns cache (AGENT_TOOL_COMPOSITION_DESIGN.md §2.2). */
public interface LearnedPatternRepositoryPort {

    /** Inserts or updates by id. */
    LearnedPattern save(LearnedPattern pattern);

    Optional<LearnedPattern> findById(UUID id);

    List<LearnedPattern> findByRobotIdAndGoal(String robotId, String goal);

    /** Highest success rate first; ties broken by more attempts first. */
    List<LearnedPattern> findByRobotIdAndGoalOrderBySuccessRateDesc(String robotId, String goal);

    List<LearnedPattern> findByRobotIdAndStatus(String robotId, PatternStatus status);

    /** The pattern for an exact, ordered tool combination (the cache key used by rollup). */
    Optional<LearnedPattern> findByRobotIdAndGoalAndToolCombination(String robotId, String goal,
                                                                     List<String> toolCombination);
}

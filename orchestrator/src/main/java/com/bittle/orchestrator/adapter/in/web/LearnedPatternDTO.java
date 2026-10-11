package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import java.time.Instant;
import java.util.List;

/** One learned tool combination for a goal, as returned to the agent (AGENT-13). */
public record LearnedPatternDTO(List<String> toolCombination, double successRate, int attempts,
                                int successes, Instant lastUsed, Instant firstDiscovered) {

    static LearnedPatternDTO from(LearnedPattern pattern) {
        return new LearnedPatternDTO(pattern.toolCombination(), pattern.successRate(),
                pattern.attempts(), pattern.successes(), pattern.lastUsed(),
                pattern.firstDiscovered());
    }
}

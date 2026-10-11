package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.LearnedPatternQueries;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import java.util.List;

/** Learned tool combinations for one robot and goal, best first (AGENT-13). */
public class GetLearnedPatternsUseCase {

    private final LearnedPatternQueries queries;

    public GetLearnedPatternsUseCase(LearnedPatternQueries queries) {
        this.queries = queries;
    }

    public List<LearnedPattern> execute(String robotId, String goal) {
        return queries.activePatterns(robotId, goal);
    }
}

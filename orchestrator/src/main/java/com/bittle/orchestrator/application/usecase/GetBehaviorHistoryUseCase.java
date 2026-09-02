package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import java.util.List;

public class GetBehaviorHistoryUseCase {

    private final BehaviorLoops loops;

    public GetBehaviorHistoryUseCase(BehaviorLoops loops) {
        this.loops = loops;
    }

    public List<BehaviorDecision> execute(String robotId, int limit) {
        return loops.loop(robotId).history(limit);
    }
}

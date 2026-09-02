package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;

public class GetBehaviorStatusUseCase {

    private final BehaviorLoops loops;

    public GetBehaviorStatusUseCase(BehaviorLoops loops) {
        this.loops = loops;
    }

    public BehaviorStatus execute(String robotId) {
        var loop = loops.loop(robotId);
        return new BehaviorStatus(robotId, loop.isRunning(), loop.personality(),
                loop.lastDecision());
    }
}

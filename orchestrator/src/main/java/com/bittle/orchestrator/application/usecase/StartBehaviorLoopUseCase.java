package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;

public class StartBehaviorLoopUseCase {

    private final BehaviorLoops loops;
    private final GetBehaviorStatusUseCase status;

    public StartBehaviorLoopUseCase(BehaviorLoops loops, GetBehaviorStatusUseCase status) {
        this.loops = loops;
        this.status = status;
    }

    public BehaviorStatus execute(String robotId) {
        loops.loop(robotId).start();
        return status.execute(robotId);
    }
}

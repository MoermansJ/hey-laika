package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;

public class StopBehaviorLoopUseCase {

    private final BehaviorLoops loops;
    private final GetBehaviorStatusUseCase status;

    public StopBehaviorLoopUseCase(BehaviorLoops loops, GetBehaviorStatusUseCase status) {
        this.loops = loops;
        this.status = status;
    }

    public BehaviorStatus execute(String robotId) {
        loops.loop(robotId).stop();
        return status.execute(robotId);
    }
}

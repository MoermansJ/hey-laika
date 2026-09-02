package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.robot.ActionResult;

public class SubmitManualActionUseCase {

    private final BehaviorLoops loops;

    public SubmitManualActionUseCase(BehaviorLoops loops) {
        this.loops = loops;
    }

    public ActionResult execute(String robotId, Action action) {
        return loops.loop(robotId).submitManualAction(action);
    }
}

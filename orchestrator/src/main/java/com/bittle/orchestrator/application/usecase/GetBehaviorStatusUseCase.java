package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.LeasePort;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;

public class GetBehaviorStatusUseCase {

    private final BehaviorLoops loops;

    public GetBehaviorStatusUseCase(BehaviorLoops loops) {
        this.loops = loops;
    }

    public BehaviorStatus execute(String robotId) {
        var loop = loops.loop(robotId);
        if (loop.isRunning()) {
            return new BehaviorStatus(robotId, true, loop.owner(), loop.personality(),
                    loop.lastDecision());
        }
        var remote = loop.remoteLease();
        return new BehaviorStatus(robotId, remote.isPresent(),
                remote.map(LeasePort.Lease::owner).orElse(null), loop.personality(),
                loop.lastDecision());
    }
}

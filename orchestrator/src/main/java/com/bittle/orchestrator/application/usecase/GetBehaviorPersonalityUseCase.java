package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.PersonalityState;

public class GetBehaviorPersonalityUseCase {

    private final BehaviorLoops loops;

    public GetBehaviorPersonalityUseCase(BehaviorLoops loops) {
        this.loops = loops;
    }

    public PersonalityState.Snapshot execute(String robotId) {
        return loops.loop(robotId).personality();
    }
}

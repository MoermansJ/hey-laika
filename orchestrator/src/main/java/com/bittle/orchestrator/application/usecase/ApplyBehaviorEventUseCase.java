package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.BehaviorEvent;
import com.bittle.orchestrator.domain.behavior.PersonalityState;

public class ApplyBehaviorEventUseCase {

    private final BehaviorLoops loops;

    public ApplyBehaviorEventUseCase(BehaviorLoops loops) {
        this.loops = loops;
    }

    public PersonalityState.Snapshot execute(String robotId, BehaviorEvent event) {
        return loops.loop(robotId).applyEvent(event);
    }
}

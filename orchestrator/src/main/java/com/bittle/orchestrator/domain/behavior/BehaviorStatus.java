package com.bittle.orchestrator.domain.behavior;

public record BehaviorStatus(String robotId, boolean running,
                             PersonalityState.Snapshot personality,
                             BehaviorDecision lastDecision) {
}

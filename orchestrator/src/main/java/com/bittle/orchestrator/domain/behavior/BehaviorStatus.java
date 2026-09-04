package com.bittle.orchestrator.domain.behavior;

public record BehaviorStatus(String robotId, boolean running, String owner,
                             PersonalityState.Snapshot personality,
                             BehaviorDecision lastDecision) {
}

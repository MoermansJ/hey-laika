package com.bittle.orchestrator.domain.behavior;

/** Behavior loop overview for one robot: running flag, personality and latest decision. */
public record BehaviorStatus(String robotId, boolean running,
                             PersonalityState.Snapshot personality,
                             BehaviorDecision lastDecision) {
}

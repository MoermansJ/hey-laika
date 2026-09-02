package com.bittle.orchestrator.domain.behavior;

/** Payload published to the robot's behavior topic after every loop cycle. */
public record BehaviorUpdate(BehaviorDecision decision, PersonalityState.Snapshot personality) {
}

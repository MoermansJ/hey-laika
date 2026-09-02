package com.bittle.orchestrator.domain.behavior;

public record BehaviorUpdate(BehaviorDecision decision, PersonalityState.Snapshot personality) {
}

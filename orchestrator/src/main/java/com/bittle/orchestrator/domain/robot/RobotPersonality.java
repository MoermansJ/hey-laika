package com.bittle.orchestrator.domain.robot;

/** Adapter-side personality snapshot (legacy adapter-owned personality). */
public record RobotPersonality(String robotId, double energy, double happiness,
                               double boredom, double curiosity, String mood) {
}

package com.bittle.orchestrator.domain.robot;

public record RobotPersonality(String robotId, double energy, double happiness,
                               double boredom, double curiosity, String mood) {
}

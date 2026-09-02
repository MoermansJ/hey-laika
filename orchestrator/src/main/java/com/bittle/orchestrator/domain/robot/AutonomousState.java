package com.bittle.orchestrator.domain.robot;

public record AutonomousState(String robotId, boolean running, Boolean changed,
                              Integer intervalSeconds) {
}

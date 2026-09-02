package com.bittle.orchestrator.domain.robot;

/** Adapter-side next-behavior suggestion (legacy adapter-owned behavior). */
public record RobotBehavior(String robotId, String behavior, String reason, String source) {
}

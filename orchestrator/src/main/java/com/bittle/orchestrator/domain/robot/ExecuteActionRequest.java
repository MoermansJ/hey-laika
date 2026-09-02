package com.bittle.orchestrator.domain.robot;

public record ExecuteActionRequest(String action, long durationMs, long sequenceId) {
}

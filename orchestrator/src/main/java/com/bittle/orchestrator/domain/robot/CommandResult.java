package com.bittle.orchestrator.domain.robot;

public record CommandResult(String robotId, String command, boolean success) {
}

package com.bittle.orchestrator.domain.robot;

public record ActionResult(String robotId, String action, boolean success,
                           Long actualDurationMs, String message) {
}

package com.bittle.orchestrator.application;

public record BehaviorSettings(long decisionIntervalMs, long sleepDecisionIntervalMs,
                               long failureBackoffMs, int historySize, boolean autoStart,
                               boolean simulateActions, boolean idleCycle) {
}

package com.bittle.orchestrator.application;

/** Tuning knobs for the autonomous behavior loops (bound from behavior.* configuration). */
public record BehaviorSettings(long decisionIntervalMs, long sleepDecisionIntervalMs,
                               long failureBackoffMs, int historySize, boolean autoStart,
                               boolean simulateActions, boolean idleCycle) {
}

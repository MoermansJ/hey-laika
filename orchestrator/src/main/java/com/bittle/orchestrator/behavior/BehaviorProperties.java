package com.bittle.orchestrator.behavior;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** Tuning knobs for the autonomous behavior loops. */
@ConfigurationProperties(prefix = "behavior")
public record BehaviorProperties(
        @DefaultValue("2500") long decisionIntervalMs,
        @DefaultValue("5000") long sleepDecisionIntervalMs,
        @DefaultValue("5000") long failureBackoffMs,
        @DefaultValue("200") int historySize,
        @DefaultValue("false") boolean autoStart,
        @DefaultValue("false") boolean simulateActions,
        @DefaultValue("false") boolean idleCycle) {
}

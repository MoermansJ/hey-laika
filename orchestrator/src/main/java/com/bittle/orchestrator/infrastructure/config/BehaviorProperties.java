package com.bittle.orchestrator.infrastructure.config;

import com.bittle.orchestrator.application.BehaviorSettings;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "behavior")
public record BehaviorProperties(
        @DefaultValue("2500") long decisionIntervalMs,
        @DefaultValue("5000") long sleepDecisionIntervalMs,
        @DefaultValue("5000") long failureBackoffMs,
        @DefaultValue("200") int historySize,
        @DefaultValue("false") boolean autoStart,
        @DefaultValue("false") boolean simulateActions,
        @DefaultValue("false") boolean idleCycle) {

    public BehaviorSettings toSettings() {
        return new BehaviorSettings(decisionIntervalMs, sleepDecisionIntervalMs, failureBackoffMs,
                historySize, autoStart, simulateActions, idleCycle);
    }
}

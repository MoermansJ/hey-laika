package com.bittle.orchestrator.infrastructure.config;

import com.bittle.orchestrator.application.MetricsSettings;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "metrics")
public record MetricsProperties(
        @DefaultValue("15.0") double claudeInputUsdPerMtok,
        @DefaultValue("75.0") double claudeOutputUsdPerMtok) {

    public MetricsSettings toSettings() {
        return new MetricsSettings(claudeInputUsdPerMtok, claudeOutputUsdPerMtok);
    }
}

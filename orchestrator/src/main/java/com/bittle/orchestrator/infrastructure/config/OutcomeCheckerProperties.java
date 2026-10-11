package com.bittle.orchestrator.infrastructure.config;

import com.bittle.orchestrator.domain.behavior.outcome.OutcomeThresholds;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** {@code agent.outcome.*}: thresholds for the goal outcome checkers (AGENT-08). */
@ConfigurationProperties(prefix = "agent.outcome")
public record OutcomeCheckerProperties(
        @DefaultValue("30") double lookCentroidPx,
        @DefaultValue("100") double lookCentroidScalePx,
        @DefaultValue("10") double lookImuDeg,
        @DefaultValue("30") double lookImuScaleDeg,
        @DefaultValue("5") double moveForwardCm,
        @DefaultValue("20") double moveForwardScaleCm,
        @DefaultValue("0.1") double listenAmplitudeDelta,
        @DefaultValue("0.3") double listenAmplitudeScale,
        @DefaultValue("0.3") double barkAmplitude,
        @DefaultValue("0.6") double barkAmplitudeScale,
        @DefaultValue("250") double barkMinHz,
        @DefaultValue("2000") double barkMaxHz,
        @DefaultValue("10") double tiltHeadDeg,
        @DefaultValue("30") double tiltHeadScaleDeg) {

    public OutcomeThresholds toThresholds() {
        return new OutcomeThresholds(lookCentroidPx, lookCentroidScalePx, lookImuDeg,
                lookImuScaleDeg, moveForwardCm, moveForwardScaleCm, listenAmplitudeDelta,
                listenAmplitudeScale, barkAmplitude, barkAmplitudeScale, barkMinHz, barkMaxHz,
                tiltHeadDeg, tiltHeadScaleDeg);
    }
}

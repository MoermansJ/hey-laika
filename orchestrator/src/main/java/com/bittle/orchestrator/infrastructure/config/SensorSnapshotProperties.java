package com.bittle.orchestrator.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** {@code agent.sensor-snapshot-ttl-minutes}: how long sensor snapshots stay cached (AGENT-09). */
@ConfigurationProperties(prefix = "agent")
public record SensorSnapshotProperties(@DefaultValue("10") long sensorSnapshotTtlMinutes) {
}

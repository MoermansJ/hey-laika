package com.bittle.orchestrator.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * HTTP timeouts for the adapter arbiter client ({@code ArbiterClient}, AGENT-04).
 * Arbiter calls only enqueue or read a row, so they stay well under the 30 s
 * command timeout of the general adapter client.
 */
@ConfigurationProperties(prefix = "arbiter")
public record ArbiterProperties(
        @DefaultValue("2000") int connectTimeoutMs,
        @DefaultValue("5000") int readTimeoutMs) {
}

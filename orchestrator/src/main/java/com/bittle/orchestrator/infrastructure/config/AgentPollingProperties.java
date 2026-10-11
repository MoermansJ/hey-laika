package com.bittle.orchestrator.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * {@code agent.*} settings for agent run polling (AGENT-10). The poll interval
 * itself ({@code agent.poll-interval-ms}) is read by the scheduler.
 *
 * @param pollBatchSize          pending runs examined per pass
 * @param runStaleAfterMinutes   a run with no completion after this long is closed as undetermined
 */
@ConfigurationProperties(prefix = "agent")
public record AgentPollingProperties(@DefaultValue("20") int pollBatchSize,
                                     @DefaultValue("10") long runStaleAfterMinutes) {
}

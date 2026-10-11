package com.bittle.orchestrator.adapter.in.scheduling;

import com.bittle.orchestrator.application.usecase.PollAgentRunsUseCase;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Polls pending agent runs for completion and evaluates their outcome
 * (AGENT-10). Every {@code agent.poll-interval-ms} (default 500 ms) after the
 * previous pass ends, so slow adapter calls never stack up passes.
 */
@Component
@ConditionalOnProperty(name = "agent.polling-enabled", havingValue = "true", matchIfMissing = true)
public class AgentRunPollScheduler {

    private final PollAgentRunsUseCase pollAgentRuns;

    public AgentRunPollScheduler(PollAgentRunsUseCase pollAgentRuns) {
        this.pollAgentRuns = pollAgentRuns;
    }

    @Scheduled(fixedDelayString = "${agent.poll-interval-ms:500}",
            initialDelayString = "${agent.poll-interval-ms:500}")
    public void poll() {
        pollAgentRuns.execute();
    }
}

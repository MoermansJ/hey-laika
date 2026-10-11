package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.AgentBehaviorService;

/** One pass of agent run completion polling and outcome evaluation (AGENT-10). */
public class PollAgentRunsUseCase {

    private final AgentBehaviorService agentBehavior;

    public PollAgentRunsUseCase(AgentBehaviorService agentBehavior) {
        this.agentBehavior = agentBehavior;
    }

    /** @return how many runs were closed */
    public int execute() {
        return agentBehavior.pollAndEvaluateCompletions();
    }
}

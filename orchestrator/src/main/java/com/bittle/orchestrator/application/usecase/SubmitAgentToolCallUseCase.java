package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.service.AgentBehaviorService;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.fleet.Fleet;
import java.util.UUID;

/** A tool call from the agent (Claude) for a declared goal (AGENT-15). */
public class SubmitAgentToolCallUseCase {

    private final Fleet fleet;
    private final AgentBehaviorService agentBehavior;

    public SubmitAgentToolCallUseCase(Fleet fleet, AgentBehaviorService agentBehavior) {
        this.fleet = fleet;
        this.agentBehavior = agentBehavior;
    }

    /**
     * @throws com.bittle.orchestrator.domain.fleet.RobotNotFoundException unknown robot
     * @throws IllegalArgumentException a decisionId that is not a UUID
     */
    public ArbiterSubmissionResponse execute(String robotId, String toolName, String goal,
                                             String decisionId) {
        fleet.get(robotId);
        UUID decision = null;
        if (decisionId != null && !decisionId.isBlank()) {
            try {
                decision = UUID.fromString(decisionId.strip());
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException("decisionId must be a UUID: " + decisionId);
            }
        }
        String declaredGoal = goal == null || goal.isBlank() ? null : goal.strip();
        String tool = toolName == null ? null : toolName.strip();
        return agentBehavior.submitToolCall(robotId, tool, declaredGoal, decision);
    }
}

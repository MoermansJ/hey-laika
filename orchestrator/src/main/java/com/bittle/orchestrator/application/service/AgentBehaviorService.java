package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.out.ArbiterPort;
import com.bittle.orchestrator.application.port.out.BehaviorRunLogRepositoryPort;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Agent tool-call lifecycle in the orchestrator (AGENT_TOOL_COMPOSITION_DESIGN.md §3.3).
 * AGENT-05 covers submission: a tool call from Claude goes to the robot's arbiter at
 * priority 3 with agent provenance, and an accepted run gets a local run-log entry
 * under the arbiter's run id so later polling and outcome evaluation can find it.
 */
public class AgentBehaviorService {

    private static final Logger log = LoggerFactory.getLogger(AgentBehaviorService.class);

    private final ArbiterPort arbiter;
    private final BehaviorRunLogRepositoryPort runLogs;
    private final Clock clock;

    public AgentBehaviorService(ArbiterPort arbiter, BehaviorRunLogRepositoryPort runLogs,
                                Clock clock) {
        this.arbiter = Objects.requireNonNull(arbiter, "arbiter");
        this.runLogs = Objects.requireNonNull(runLogs, "runLogs");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    /**
     * Submit an agent-sourced tool call to the arbiter.
     *
     * @param robotId      robot to act
     * @param toolName     named behavior to run
     * @param declaredGoal goal the agent wants the tool call to achieve (may be null)
     * @param decisionId   the agent decision this call belongs to; a fresh id is used when null
     * @return the arbiter's answer; a rejection when the adapter refused or was unreachable
     */
    public ArbiterSubmissionResponse submitToolCall(String robotId, String toolName,
                                                    String declaredGoal, UUID decisionId) {
        Objects.requireNonNull(robotId, "robotId");
        if (toolName == null || toolName.isBlank()) {
            return ArbiterSubmissionResponse.rejected("toolName is required");
        }
        UUID decision = decisionId != null ? decisionId : UUID.randomUUID();
        var request = ArbiterSubmissionRequest.forAgent(toolName, declaredGoal,
                decision.toString());

        ArbiterSubmissionResponse response = arbiter.submit(robotId, request);
        if (response == null) {
            return ArbiterSubmissionResponse.rejected("Empty arbiter response");
        }
        if (!response.isAccepted()) {
            log.info("Agent tool call {} for {} (goal {}) rejected: {}", toolName, robotId,
                    declaredGoal, response.message());
            return response;
        }
        if (response.runLogId() == null) {
            // Without the arbiter's run id the entry could never be matched when polling.
            log.warn("Agent tool call {} for {} accepted ({}) without a run id; no run-log entry",
                    toolName, robotId, response.status());
            return response;
        }
        record(robotId, request, response.runLogId());
        log.info("Agent tool call {} for {} (goal {}, decision {}) -> {} run {}", toolName,
                robotId, declaredGoal, decision, response.status(), response.runLogId());
        return response;
    }

    private void record(String robotId, ArbiterSubmissionRequest request, UUID runLogId) {
        Instant now = clock.instant();
        var entry = new BehaviorRunLog(runLogId, robotId, now, null, request.behaviorName(),
                request.source(), request.priority(), request.cause(), null, null,
                request.goal(), null, null, now, now);
        try {
            runLogs.save(entry);
        } catch (RuntimeException e) {
            // The arbiter already accepted the run; the robot moves either way.
            log.error("Could not store run-log entry {} for {}: {}", runLogId, robotId,
                    e.getMessage(), e);
        }
    }
}

package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import java.util.UUID;

/**
 * The arbiter's answer to a tool call (AGENT-15): status executing | queued |
 * preempting | rejected, the run id when accepted, the reason when rejected.
 */
public record ToolCallResponse(UUID runLogId, String status, String message, Integer position) {

    static ToolCallResponse from(ArbiterSubmissionResponse response) {
        return new ToolCallResponse(response.runLogId(), response.status(), response.message(),
                response.position());
    }
}

package com.bittle.orchestrator.domain.behavior;

import java.util.Objects;
import java.util.UUID;

/**
 * The arbiter's answer to a submission (AGENT_TOOL_COMPOSITION_DESIGN.md §2.3).
 *
 * @param runLogId id the run-log entry carries once the run starts; null when rejected
 *                 or when the adapter did not report one
 * @param status   "executing" | "queued" | "preempting" | "rejected"
 * @param message  reason when rejected, otherwise null
 * @param position queue position reported by the arbiter, or null
 */
public record ArbiterSubmissionResponse(UUID runLogId, String status, String message,
                                        Integer position) {

    public static final String EXECUTING = "executing";
    public static final String QUEUED = "queued";
    public static final String PREEMPTING = "preempting";
    public static final String REJECTED = "rejected";

    public ArbiterSubmissionResponse {
        Objects.requireNonNull(status, "status");
    }

    /** A rejection that never reached (or was refused by) the arbiter. */
    public static ArbiterSubmissionResponse rejected(String message) {
        return new ArbiterSubmissionResponse(null, REJECTED, message, null);
    }

    /** True when the arbiter accepted the behavior (executing, queued or preempting). */
    public boolean isAccepted() {
        return !REJECTED.equals(status);
    }
}

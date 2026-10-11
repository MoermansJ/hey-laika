package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import java.util.Optional;
import java.util.UUID;

/**
 * The robot adapter's behavior arbiter (AGENT_TOOL_COMPOSITION_DESIGN.md §5.1).
 * Implementations never throw for adapter or network failures: a failed
 * submission comes back as a rejected response, a failed read as empty and a
 * failed outcome sync as false, so callers on polling paths keep running.
 */
public interface ArbiterPort {

    /** Submit a named behavior to the robot's arbiter. */
    ArbiterSubmissionResponse submit(String robotId, ArbiterSubmissionRequest request);

    /**
     * The run-log entry for a submitted run, or empty when the adapter does not
     * (yet) have it — a queued run has no entry until it starts — or cannot be reached.
     */
    Optional<BehaviorRunLog> getRunLog(String robotId, UUID runLogId);

    /** Write the orchestrator's outcome evaluation back to the adapter; true on success. */
    boolean syncOutcome(String robotId, UUID runLogId, OutcomeEvaluation outcome);
}

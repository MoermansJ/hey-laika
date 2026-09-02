package com.bittle.orchestrator.application.port.in;

import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import com.bittle.orchestrator.domain.behavior.BehaviorEvent;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.bittle.orchestrator.domain.robot.ActionResult;
import java.util.List;

/**
 * Orchestrator-owned behavior and personality of each robot. The personality
 * state exists as soon as anything touches it; the loop runs only on request.
 */
public interface BehaviorUseCase {

    PersonalityState.Snapshot personality(String robotId);

    BehaviorStatus status(String robotId);

    List<BehaviorDecision> history(String robotId, int limit);

    BehaviorStatus start(String robotId);

    BehaviorStatus stop(String robotId);

    boolean isRunning(String robotId);

    /** Applies an external owner/sensor event; works whether or not the loop runs. */
    PersonalityState.Snapshot applyEvent(String robotId, BehaviorEvent event);

    /**
     * With the loop running the action is queued ahead of autonomous decisions;
     * with the loop stopped it executes immediately.
     */
    ActionResult submitManualAction(String robotId, Action action);

    /** Starts every robot's loop when auto-start is configured; otherwise a no-op. */
    void autoStart();
}

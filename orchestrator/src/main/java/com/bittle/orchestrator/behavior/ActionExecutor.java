package com.bittle.orchestrator.behavior;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.dto.Dtos.ActionResult;
import com.bittle.orchestrator.dto.Dtos.ExecuteActionRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Sends actions to the robot's Python adapter and normalizes failures: an
 * unreachable or erroring adapter yields a failed {@link ActionResult} instead
 * of an exception, so the behavior loop can keep running and back off.
 */
@Component
public class ActionExecutor {

    private static final Logger log = LoggerFactory.getLogger(ActionExecutor.class);

    private final BehaviorProperties properties;

    public ActionExecutor(BehaviorProperties properties) {
        this.properties = properties;
    }

    public ActionResult execute(RobotAgent agent, Action action, long sequenceId) {
        if (properties.simulateActions()) {
            return simulate(agent.id(), action);
        }
        var request = new ExecuteActionRequest(action.actionId(), action.durationMs(), sequenceId);
        try {
            var result = agent.executeAction(request);
            if (result == null) {
                return failed(agent.id(), action, "empty adapter response");
            }
            return result;
        } catch (RuntimeException e) {
            log.warn("Action {} on {} failed: {}", action.actionId(), agent.id(), e.getMessage());
            return failed(agent.id(), action, e.getMessage());
        }
    }

    /** Dev mode (behavior.simulate-actions): pretend to execute, pacing like the real robot. */
    private ActionResult simulate(String robotId, Action action) {
        try {
            Thread.sleep(action.durationMs());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return failed(robotId, action, "interrupted");
        }
        return new ActionResult(robotId, action.actionId(), true, action.durationMs(), "simulated");
    }

    private static ActionResult failed(String robotId, Action action, String message) {
        return new ActionResult(robotId, action.actionId(), false, null, message);
    }
}

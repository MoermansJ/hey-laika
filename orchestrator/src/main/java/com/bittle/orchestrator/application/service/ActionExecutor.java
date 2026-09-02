package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.ExecuteActionRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Sends actions to the robot's adapter and normalizes failures: an
 * unreachable or erroring adapter yields a failed {@link ActionResult} instead
 * of an exception, so the behavior loop can keep running and back off.
 */
public class ActionExecutor {

    private static final Logger log = LoggerFactory.getLogger(ActionExecutor.class);

    private final RobotAdapterPort adapter;
    private final BehaviorSettings settings;

    public ActionExecutor(RobotAdapterPort adapter, BehaviorSettings settings) {
        this.adapter = adapter;
        this.settings = settings;
    }

    public ActionResult execute(Robot robot, Action action, long sequenceId) {
        if (settings.simulateActions()) {
            return simulate(robot.id(), action);
        }
        var request = new ExecuteActionRequest(action.actionId(), action.durationMs(), sequenceId);
        try {
            var result = adapter.executeAction(robot, request);
            if (result == null) {
                return failed(robot.id(), action, "empty adapter response");
            }
            return result;
        } catch (RuntimeException e) {
            log.warn("Action {} on {} failed: {}", action.actionId(), robot.id(), e.getMessage());
            return failed(robot.id(), action, e.getMessage());
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

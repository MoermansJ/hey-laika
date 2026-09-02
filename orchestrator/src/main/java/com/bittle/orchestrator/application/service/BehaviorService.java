package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.port.in.BehaviorUseCase;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import com.bittle.orchestrator.domain.behavior.BehaviorEvent;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;
import com.bittle.orchestrator.domain.behavior.DecisionEngine;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.bittle.orchestrator.domain.behavior.PersonalityStateManager;
import com.bittle.orchestrator.domain.robot.ActionResult;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Owns one {@link RobotBehaviorLoop} per robot. Loops are created lazily (the
 * personality state exists as soon as anything touches it) and started only on
 * request — or at boot when auto-start is configured.
 */
public class BehaviorService implements BehaviorUseCase {

    private static final Logger log = LoggerFactory.getLogger(BehaviorService.class);

    private final FleetRegistry registry;
    private final PersonalityStateManager stateManager;
    private final DecisionEngine decisionEngine;
    private final ActionExecutor executor;
    private final EventPublisherPort publisher;
    private final BehaviorSettings settings;

    private final Map<String, RobotBehaviorLoop> loops = new ConcurrentHashMap<>();

    public BehaviorService(FleetRegistry registry, PersonalityStateManager stateManager,
                           DecisionEngine decisionEngine, ActionExecutor executor,
                           EventPublisherPort publisher, BehaviorSettings settings) {
        this.registry = registry;
        this.stateManager = stateManager;
        this.decisionEngine = decisionEngine;
        this.executor = executor;
        this.publisher = publisher;
        this.settings = settings;
    }

    @Override
    public PersonalityState.Snapshot personality(String robotId) {
        return loop(robotId).personality();
    }

    @Override
    public BehaviorStatus status(String robotId) {
        var loop = loop(robotId);
        return new BehaviorStatus(robotId, loop.isRunning(), loop.personality(),
                loop.lastDecision());
    }

    @Override
    public List<BehaviorDecision> history(String robotId, int limit) {
        return loop(robotId).history(limit);
    }

    @Override
    public BehaviorStatus start(String robotId) {
        loop(robotId).start();
        return status(robotId);
    }

    @Override
    public BehaviorStatus stop(String robotId) {
        loop(robotId).stop();
        return status(robotId);
    }

    @Override
    public boolean isRunning(String robotId) {
        return loop(robotId).isRunning();
    }

    @Override
    public PersonalityState.Snapshot applyEvent(String robotId, BehaviorEvent event) {
        return loop(robotId).applyEvent(event);
    }

    @Override
    public ActionResult submitManualAction(String robotId, Action action) {
        return loop(robotId).submitManualAction(action);
    }

    @Override
    public void autoStart() {
        if (!settings.autoStart()) {
            return;
        }
        registry.all().forEach(robot -> loop(robot.id()).start());
        log.info("Auto-started {} behavior loop(s)", registry.all().size());
    }

    /** Stops every loop; wired as the bean's destroy method. */
    public void shutdown() {
        loops.values().forEach(RobotBehaviorLoop::stop);
    }

    /** Creates the loop on first access; throws RobotNotFoundException for unknown ids. */
    private RobotBehaviorLoop loop(String robotId) {
        var robot = registry.get(robotId);
        return loops.computeIfAbsent(robotId, id -> new RobotBehaviorLoop(robot, stateManager,
                decisionEngine, executor, publisher, settings));
    }
}

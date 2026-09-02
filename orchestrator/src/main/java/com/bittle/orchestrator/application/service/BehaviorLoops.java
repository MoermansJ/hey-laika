package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.domain.behavior.DecisionEngine;
import com.bittle.orchestrator.domain.behavior.PersonalityStateManager;
import java.util.Collection;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class BehaviorLoops {

    private final FleetRegistry registry;
    private final PersonalityStateManager stateManager;
    private final DecisionEngine decisionEngine;
    private final ActionExecutor executor;
    private final EventPublisherPort publisher;
    private final BehaviorSettings settings;

    private final Map<String, RobotBehaviorLoop> loops = new ConcurrentHashMap<>();

    public BehaviorLoops(FleetRegistry registry, PersonalityStateManager stateManager,
                         DecisionEngine decisionEngine, ActionExecutor executor,
                         EventPublisherPort publisher, BehaviorSettings settings) {
        this.registry = registry;
        this.stateManager = stateManager;
        this.decisionEngine = decisionEngine;
        this.executor = executor;
        this.publisher = publisher;
        this.settings = settings;
    }

    public RobotBehaviorLoop loop(String robotId) {
        var robot = registry.get(robotId);
        return loops.computeIfAbsent(robotId, id -> new RobotBehaviorLoop(robot, stateManager,
                decisionEngine, executor, publisher, settings));
    }

    public Collection<RobotBehaviorLoop> all() {
        return loops.values();
    }

    public void shutdown() {
        loops.values().forEach(RobotBehaviorLoop::stop);
    }
}

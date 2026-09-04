package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.InstanceIdentity;
import com.bittle.orchestrator.application.port.out.DecisionHistoryRepositoryPort;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.LeasePort;
import com.bittle.orchestrator.application.port.out.PersonalityStateRepositoryPort;
import com.bittle.orchestrator.domain.behavior.DecisionEngine;
import com.bittle.orchestrator.domain.behavior.PersonalityStateManager;
import com.bittle.orchestrator.domain.fleet.Fleet;
import java.util.Collection;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class BehaviorLoops {

    private final Fleet fleet;
    private final PersonalityStateManager stateManager;
    private final DecisionEngine decisionEngine;
    private final ActionExecutor executor;
    private final EventPublisherPort publisher;
    private final BehaviorSettings settings;
    private final PersonalityStateRepositoryPort states;
    private final DecisionHistoryRepositoryPort decisions;
    private final LeasePort leases;
    private final InstanceIdentity identity;

    private final Map<String, RobotBehaviorLoop> loops = new ConcurrentHashMap<>();

    public BehaviorLoops(Fleet fleet, PersonalityStateManager stateManager,
                         DecisionEngine decisionEngine, ActionExecutor executor,
                         EventPublisherPort publisher, BehaviorSettings settings,
                         PersonalityStateRepositoryPort states,
                         DecisionHistoryRepositoryPort decisions, LeasePort leases,
                         InstanceIdentity identity) {
        this.fleet = fleet;
        this.stateManager = stateManager;
        this.decisionEngine = decisionEngine;
        this.executor = executor;
        this.publisher = publisher;
        this.settings = settings;
        this.states = states;
        this.decisions = decisions;
        this.leases = leases;
        this.identity = identity;
    }

    public RobotBehaviorLoop loop(String robotId) {
        var robot = fleet.get(robotId);
        return loops.computeIfAbsent(robotId, id -> new RobotBehaviorLoop(robot, stateManager,
                decisionEngine, executor, publisher, settings, states, decisions, leases,
                identity));
    }

    public Collection<RobotBehaviorLoop> all() {
        return loops.values();
    }

    public void shutdown() {
        loops.values().forEach(RobotBehaviorLoop::stop);
    }
}

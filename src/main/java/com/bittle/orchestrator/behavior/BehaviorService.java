package com.bittle.orchestrator.behavior;

import com.bittle.orchestrator.fleet.FleetManager;
import jakarta.annotation.PreDestroy;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

/**
 * Owns one {@link RobotBehaviorLoop} per robot. Loops are created lazily (the
 * personality state exists as soon as anything touches it) and started only on
 * request — or at boot when behavior.auto-start=true.
 */
@Service
public class BehaviorService {

    private static final Logger log = LoggerFactory.getLogger(BehaviorService.class);

    private final FleetManager fleetManager;
    private final PersonalityStateManager stateManager;
    private final DecisionEngine decisionEngine;
    private final ActionExecutor executor;
    private final SimpMessagingTemplate messaging;
    private final BehaviorProperties properties;

    private final Map<String, RobotBehaviorLoop> loops = new ConcurrentHashMap<>();

    public BehaviorService(FleetManager fleetManager, PersonalityStateManager stateManager,
                           DecisionEngine decisionEngine, ActionExecutor executor,
                           SimpMessagingTemplate messaging, BehaviorProperties properties) {
        this.fleetManager = fleetManager;
        this.stateManager = stateManager;
        this.decisionEngine = decisionEngine;
        this.executor = executor;
        this.messaging = messaging;
        this.properties = properties;
    }

    /** Creates the loop on first access; throws RobotNotFoundException for unknown ids. */
    public RobotBehaviorLoop loop(String robotId) {
        var agent = fleetManager.get(robotId);
        return loops.computeIfAbsent(robotId, id -> new RobotBehaviorLoop(agent, stateManager,
                decisionEngine, executor, messaging, properties));
    }

    @EventListener(ApplicationReadyEvent.class)
    public void autoStart() {
        if (!properties.autoStart()) {
            return;
        }
        for (var agent : fleetManager.all()) {
            loop(agent.id()).start();
        }
        log.info("Auto-started {} behavior loop(s)", fleetManager.all().size());
    }

    @PreDestroy
    public void shutdown() {
        loops.values().forEach(RobotBehaviorLoop::stop);
    }
}

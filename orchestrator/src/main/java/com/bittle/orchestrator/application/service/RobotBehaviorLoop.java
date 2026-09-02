package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision.DecisionSource;
import com.bittle.orchestrator.domain.behavior.BehaviorEvent;
import com.bittle.orchestrator.domain.behavior.BehaviorUpdate;
import com.bittle.orchestrator.domain.behavior.DecisionEngine;
import com.bittle.orchestrator.domain.behavior.DecisionEngine.Decision;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.bittle.orchestrator.domain.behavior.PersonalityStateManager;
import com.bittle.orchestrator.domain.behavior.Posture;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.ActionResult;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RobotBehaviorLoop {

    private static final Logger log = LoggerFactory.getLogger(RobotBehaviorLoop.class);

    private final Robot robot;
    private final PersonalityStateManager stateManager;
    private final DecisionEngine decisionEngine;
    private final ActionExecutor executor;
    private final EventPublisherPort publisher;
    private final BehaviorSettings settings;

    private final PersonalityState state = new PersonalityState();
    private final Object stateLock = new Object();
    private final LinkedBlockingQueue<Action> manualQueue = new LinkedBlockingQueue<>();
    private final ConcurrentLinkedDeque<BehaviorDecision> history = new ConcurrentLinkedDeque<>();
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicLong sequence = new AtomicLong();

    private volatile Thread thread;

    public RobotBehaviorLoop(Robot robot, PersonalityStateManager stateManager,
                             DecisionEngine decisionEngine, ActionExecutor executor,
                             EventPublisherPort publisher, BehaviorSettings settings) {
        this.robot = robot;
        this.stateManager = stateManager;
        this.decisionEngine = decisionEngine;
        this.executor = executor;
        this.publisher = publisher;
        this.settings = settings;
    }

    public synchronized void start() {
        if (running.get()) {
            return;
        }
        running.set(true);
        thread = new Thread(this::run, "behavior-" + robot.id());
        thread.setDaemon(true);
        thread.start();
        log.info("Behavior loop started for {}", robot.id());
    }

    public synchronized void stop() {
        if (!running.getAndSet(false)) {
            return;
        }
        var t = thread;
        if (t != null) {
            t.interrupt();
        }
        log.info("Behavior loop stopped for {}", robot.id());
    }

    public boolean isRunning() {
        return running.get();
    }

    public PersonalityState.Snapshot personality() {
        synchronized (stateLock) {
            return state.snapshot(robot.id());
        }
    }

    public BehaviorDecision lastDecision() {
        return history.peekFirst();
    }

    public List<BehaviorDecision> history(int limit) {
        return history.stream().limit(limit).toList();
    }

    public PersonalityState.Snapshot applyEvent(BehaviorEvent event) {
        synchronized (stateLock) {
            stateManager.applyEvent(state, event, Instant.now());
            return state.snapshot(robot.id());
        }
    }

    public ActionResult submitManualAction(Action action) {
        if (running.get()) {
            manualQueue.offer(action);
            return new ActionResult(robot.id(), action.actionId(), true, null, "queued");
        }
        return performAction(action, DecisionSource.MANUAL, "manual action (loop stopped)");
    }

    private void run() {
        while (running.get()) {
            try {
                cycle();
                long interval = currentPosture() == Posture.SLEEPING
                        ? settings.sleepDecisionIntervalMs()
                        : settings.decisionIntervalMs();
                Thread.sleep(interval);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } catch (RuntimeException e) {
                log.error("Behavior cycle failed for {}: {}", robot.id(), e.getMessage(), e);
                sleepQuietly(settings.failureBackoffMs());
            }
        }
    }

    private void cycle() {
        var manual = manualQueue.poll();
        if (manual != null) {
            performAction(manual, DecisionSource.MANUAL, "manual action");
            return;
        }

        Decision decision;
        synchronized (stateLock) {
            decision = decisionEngine.decide(state);
        }
        if (decision.action() == null) {
            synchronized (stateLock) {
                stateManager.applyPassiveDrift(state, Instant.now());
            }
            record(null, decision.source(), decision.reasoning(), null);
            return;
        }
        var result = performAction(decision.action(), decision.source(), decision.reasoning());
        if (!result.success()) {
            sleepQuietly(settings.failureBackoffMs());
        }
    }

    private ActionResult performAction(Action action, DecisionSource source, String reasoning) {
        synchronized (stateLock) {
            if (!action.validFor(state.posture(), state.energy())) {
                var rejected = new ActionResult(robot.id(), action.actionId(), false, null,
                        "invalid from posture " + state.posture());
                record(action, source, reasoning + " — rejected: " + rejected.message(), rejected);
                return rejected;
            }
        }
        var result = executor.execute(robot, action, sequence.incrementAndGet());
        synchronized (stateLock) {
            stateManager.onActionCompleted(state, action, result.success(), Instant.now());
            stateManager.applyPassiveDrift(state, Instant.now());
        }
        record(action, source, reasoning, result);
        return result;
    }

    private void record(Action action, DecisionSource source, String reasoning,
                        ActionResult result) {
        PersonalityState.Snapshot snapshot;
        List<String> validActions;
        synchronized (stateLock) {
            snapshot = state.snapshot(robot.id());
            validActions = Action.validActions(state.posture(), state.energy()).stream()
                    .map(Action::actionId).toList();
        }
        var decision = new BehaviorDecision(robot.id(), Instant.now(), snapshot, validActions,
                action == null ? null : action.actionId(), source, reasoning,
                result == null ? null : result.success(),
                result == null ? null : result.actualDurationMs());
        history.addFirst(decision);
        while (history.size() > settings.historySize()) {
            history.pollLast();
        }
        log.info("[{}] {} {} ({}){} | energy={} happy={} bored={} curious={} hunger={} content={} posture={}",
                robot.id(), source,
                action == null ? "-rest-" : action.actionId(), reasoning,
                result != null && !result.success() ? " FAILED: " + result.message() : "",
                pct(snapshot.energy()), pct(snapshot.happiness()), pct(snapshot.boredom()),
                pct(snapshot.curiosity()), pct(snapshot.hunger()), pct(snapshot.contentment()),
                snapshot.posture());
        publish(decision, snapshot);
    }

    private void publish(BehaviorDecision decision, PersonalityState.Snapshot snapshot) {
        try {
            publisher.publish("/topic/robot/" + robot.id() + "/behavior",
                    new BehaviorUpdate(decision, snapshot));
        } catch (RuntimeException e) {
            log.debug("Behavior broadcast failed for {}: {}", robot.id(), e.getMessage());
        }
    }

    private Posture currentPosture() {
        synchronized (stateLock) {
            return state.posture();
        }
    }

    private static String pct(double value) {
        return Math.round(value * 100) + "%";
    }

    private static void sleepQuietly(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}

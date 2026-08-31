package com.bittle.orchestrator.behavior;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.behavior.BehaviorDecision.DecisionSource;
import com.bittle.orchestrator.behavior.DecisionEngine.Decision;
import com.bittle.orchestrator.dto.Dtos.ActionResult;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.simp.SimpMessagingTemplate;

/**
 * The autonomous brain of one robot. Owns the robot's {@link PersonalityState}
 * (which exists and accepts events even while the loop is stopped), runs the
 * decide → execute → update cycle on its own thread, and drains manual actions
 * before making autonomous decisions so manual control and autonomy never race
 * on the servos.
 */
public class RobotBehaviorLoop {

    private static final Logger log = LoggerFactory.getLogger(RobotBehaviorLoop.class);

    private final RobotAgent agent;
    private final PersonalityStateManager stateManager;
    private final DecisionEngine decisionEngine;
    private final ActionExecutor executor;
    private final SimpMessagingTemplate messaging;
    private final BehaviorProperties properties;

    private final PersonalityState state = new PersonalityState();
    private final Object stateLock = new Object();
    private final LinkedBlockingQueue<Action> manualQueue = new LinkedBlockingQueue<>();
    private final ConcurrentLinkedDeque<BehaviorDecision> history = new ConcurrentLinkedDeque<>();
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicLong sequence = new AtomicLong();

    private volatile Thread thread;

    public RobotBehaviorLoop(RobotAgent agent, PersonalityStateManager stateManager,
                             DecisionEngine decisionEngine, ActionExecutor executor,
                             SimpMessagingTemplate messaging, BehaviorProperties properties) {
        this.agent = agent;
        this.stateManager = stateManager;
        this.decisionEngine = decisionEngine;
        this.executor = executor;
        this.messaging = messaging;
        this.properties = properties;
    }

    public synchronized void start() {
        if (running.get()) {
            return;
        }
        running.set(true);
        thread = new Thread(this::run, "behavior-" + agent.id());
        thread.setDaemon(true);
        thread.start();
        log.info("Behavior loop started for {}", agent.id());
    }

    public synchronized void stop() {
        if (!running.getAndSet(false)) {
            return;
        }
        var t = thread;
        if (t != null) {
            t.interrupt();
        }
        log.info("Behavior loop stopped for {}", agent.id());
    }

    public boolean isRunning() {
        return running.get();
    }

    public PersonalityState.Snapshot personality() {
        synchronized (stateLock) {
            return state.snapshot(agent.id());
        }
    }

    public BehaviorDecision lastDecision() {
        return history.peekFirst();
    }

    public List<BehaviorDecision> history(int limit) {
        var result = new ArrayList<BehaviorDecision>(Math.min(limit, history.size()));
        for (var decision : history) {
            if (result.size() >= limit) {
                break;
            }
            result.add(decision);
        }
        return result;
    }

    /** Applies an external owner/sensor event; works whether or not the loop runs. */
    public PersonalityState.Snapshot applyEvent(BehaviorEvent event) {
        synchronized (stateLock) {
            stateManager.applyEvent(state, event, Instant.now());
            return state.snapshot(agent.id());
        }
    }

    /**
     * Manual action entry point. With the loop running the action is queued and
     * executed ahead of autonomous decisions; with the loop stopped it executes
     * immediately on the caller's thread.
     */
    public ActionResult submitManualAction(Action action) {
        if (running.get()) {
            manualQueue.offer(action);
            return new ActionResult(agent.id(), action.actionId(), true, null, "queued");
        }
        return performAction(action, DecisionSource.MANUAL, "manual action (loop stopped)");
    }

    private void run() {
        while (running.get()) {
            try {
                cycle();
                long interval = currentPosture() == Posture.SLEEPING
                        ? properties.sleepDecisionIntervalMs()
                        : properties.decisionIntervalMs();
                Thread.sleep(interval);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } catch (RuntimeException e) {
                log.error("Behavior cycle failed for {}: {}", agent.id(), e.getMessage(), e);
                sleepQuietly(properties.failureBackoffMs());
            }
        }
    }

    private void cycle() {
        Action manual = manualQueue.poll();
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
            sleepQuietly(properties.failureBackoffMs());
        }
    }

    private ActionResult performAction(Action action, DecisionSource source, String reasoning) {
        synchronized (stateLock) {
            if (!action.validFor(state.posture(), state.energy())) {
                var rejected = new ActionResult(agent.id(), action.actionId(), false, null,
                        "invalid from posture " + state.posture());
                record(action, source, reasoning + " — rejected: " + rejected.message(), rejected);
                return rejected;
            }
        }
        var result = executor.execute(agent, action, sequence.incrementAndGet());
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
            snapshot = state.snapshot(agent.id());
            validActions = Action.validActions(state.posture(), state.energy()).stream()
                    .map(Action::actionId).toList();
        }
        var decision = new BehaviorDecision(agent.id(), Instant.now(), snapshot, validActions,
                action == null ? null : action.actionId(), source, reasoning,
                result == null ? null : result.success(),
                result == null ? null : result.actualDurationMs());
        history.addFirst(decision);
        while (history.size() > properties.historySize()) {
            history.pollLast();
        }
        log.info("[{}] {} {} ({}){} | energy={} happy={} bored={} curious={} hunger={} content={} posture={}",
                agent.id(), source,
                action == null ? "-rest-" : action.actionId(), reasoning,
                result != null && !result.success() ? " FAILED: " + result.message() : "",
                pct(snapshot.energy()), pct(snapshot.happiness()), pct(snapshot.boredom()),
                pct(snapshot.curiosity()), pct(snapshot.hunger()), pct(snapshot.contentment()),
                snapshot.posture());
        publish(decision, snapshot);
    }

    private void publish(BehaviorDecision decision, PersonalityState.Snapshot snapshot) {
        try {
            messaging.convertAndSend("/topic/robot/" + agent.id() + "/behavior",
                    new BehaviorUpdate(decision, snapshot));
        } catch (RuntimeException e) {
            log.debug("Behavior broadcast failed for {}: {}", agent.id(), e.getMessage());
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

    /** STOMP payload published after every cycle. */
    public record BehaviorUpdate(BehaviorDecision decision,
                                 PersonalityState.Snapshot personality) {
    }
}

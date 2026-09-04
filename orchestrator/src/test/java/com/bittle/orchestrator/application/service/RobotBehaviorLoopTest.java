package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

import com.bittle.orchestrator.application.BehaviorLoopHeldElsewhereException;
import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.InstanceIdentity;
import com.bittle.orchestrator.application.port.out.DecisionHistoryRepositoryPort;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.LeasePort;
import com.bittle.orchestrator.application.port.out.PersonalityStateRepositoryPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import com.bittle.orchestrator.domain.behavior.BehaviorEvent;
import com.bittle.orchestrator.domain.behavior.DecisionEngine;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.bittle.orchestrator.domain.behavior.PersonalityStateManager;
import com.bittle.orchestrator.domain.behavior.Posture;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class RobotBehaviorLoopTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");
    private static final String KEY = "behavior-loop:bittle-1";
    private static final BehaviorSettings SETTINGS =
            new BehaviorSettings(50, 50, 50, 20, false, true, false, 60_000);

    private final InMemoryStates states = new InMemoryStates();
    private final InMemoryDecisions decisions = new InMemoryDecisions();
    private final InMemoryLeases leases = new InMemoryLeases();
    private final EventPublisherPort publisher = mock(EventPublisherPort.class);
    private final DecisionEngine restingEngine = state -> DecisionEngine.Decision.rest("resting");
    private final List<RobotBehaviorLoop> started = new ArrayList<>();

    @AfterEach
    void stopLoops() {
        started.forEach(RobotBehaviorLoop::stop);
    }

    @Test
    void givenStoredState_whenStarted_thenStateIsLoadedAndTheLeaseIsHeld() {
        states.save(new PersonalityState.Snapshot("bittle-1", 0.1, 0.2, 0.3, 0.4, 0.5, 0.6,
                Posture.SITTING, "sit_down", Instant.now(), Instant.now(), 7));
        var loop = loop("instance-a");

        loop.start();
        started.add(loop);

        assertThat(loop.isRunning()).isTrue();
        assertThat(loop.personality().energy()).isEqualTo(0.1);
        assertThat(loop.personality().posture()).isEqualTo(Posture.SITTING);
        assertThat(leases.holder(KEY)).map(LeasePort.Lease::owner).contains("instance-a");
    }

    @Test
    void givenRunningLoop_whenStopped_thenTheLeaseIsReleased() {
        var loop = loop("instance-a");
        loop.start();

        loop.stop();

        assertThat(loop.isRunning()).isFalse();
        assertThat(leases.holder(KEY)).isEmpty();
    }

    @Test
    void givenLeaseHeldElsewhere_whenStarted_thenItIsRefusedAndStaysStopped() {
        leases.acquire(KEY, "instance-b", Duration.ofMinutes(1));
        var loop = loop("instance-a");

        assertThatThrownBy(loop::start)
                .isInstanceOf(BehaviorLoopHeldElsewhereException.class)
                .hasMessageContaining("instance-b");
        assertThat(loop.isRunning()).isFalse();
        assertThat(loop.remoteLease()).map(LeasePort.Lease::owner).contains("instance-b");
    }

    @Test
    void givenLoopStopped_whenEventApplied_thenTheStateIsWrittenThrough() {
        var loop = loop("instance-a");

        var snapshot = loop.applyEvent(BehaviorEvent.OWNER_PETTED);

        assertThat(snapshot.happiness()).isGreaterThan(0.7);
        assertThat(states.find("bittle-1")).contains(snapshot);
        assertThat(loop.personality()).isEqualTo(snapshot);
    }

    @Test
    void givenLoopHeldElsewhere_whenEventApplied_thenItIsRefused() {
        leases.acquire(KEY, "instance-b", Duration.ofMinutes(1));

        assertThatThrownBy(() -> loop("instance-a").applyEvent(BehaviorEvent.OWNER_PETTED))
                .isInstanceOf(BehaviorLoopHeldElsewhereException.class);
        assertThat(states.find("bittle-1")).isEmpty();
    }

    @Test
    void givenLoopStopped_whenManualActionRuns_thenTheDecisionIsPersistedAndServedFromStorage() {
        var loop = loop("instance-a");

        var result = loop.submitManualAction(Action.LOOK_LEFT);

        assertThat(result.success()).isTrue();
        assertThat(decisions.findLatest("bittle-1", 10))
                .extracting(BehaviorDecision::selectedAction)
                .containsExactly("look_left");
        assertThat(loop.history(10)).hasSize(1);
        assertThat(loop.lastDecision().selectedAction()).isEqualTo("look_left");
        assertThat(states.find("bittle-1")).map(PersonalityState.Snapshot::lastAction)
                .contains("look_left");
    }

    @Test
    void givenRunningLoop_whenOnlyResting_thenStateIsSavedButNoDecisionRowIsWritten()
            throws InterruptedException {
        var loop = loop("instance-a");
        loop.start();
        started.add(loop);

        Thread.sleep(200);

        assertThat(states.saves.get()).isGreaterThan(0);
        assertThat(decisions.rows).isEmpty();
        assertThat(loop.history(10)).isNotEmpty();
    }

    @Test
    void givenRunningLoop_whenTheLeaseIsTakenOver_thenTheLoopStopsItself() throws InterruptedException {
        var loop = loop("instance-a");
        loop.start();
        started.add(loop);

        leases.force(KEY, "instance-b");

        var deadline = System.currentTimeMillis() + 3000;
        while (loop.isRunning() && System.currentTimeMillis() < deadline) {
            Thread.sleep(20);
        }
        assertThat(loop.isRunning()).isFalse();
        assertThat(leases.holder(KEY)).map(LeasePort.Lease::owner).contains("instance-b");
    }

    private RobotBehaviorLoop loop(String instance) {
        return new RobotBehaviorLoop(LAIKA, new PersonalityStateManager(), restingEngine,
                new ActionExecutor(mock(RobotAdapterPort.class), SETTINGS), publisher, SETTINGS,
                states, decisions, leases, new InstanceIdentity(instance));
    }

    private static final class InMemoryStates implements PersonalityStateRepositoryPort {

        private final Map<String, PersonalityState.Snapshot> rows = new ConcurrentHashMap<>();
        private final AtomicInteger saves = new AtomicInteger();

        @Override
        public Optional<PersonalityState.Snapshot> find(String robotId) {
            return Optional.ofNullable(rows.get(robotId));
        }

        @Override
        public void save(PersonalityState.Snapshot snapshot) {
            rows.put(snapshot.robotId(), snapshot);
            saves.incrementAndGet();
        }
    }

    private static final class InMemoryDecisions implements DecisionHistoryRepositoryPort {

        private final List<BehaviorDecision> rows = Collections.synchronizedList(new ArrayList<>());

        @Override
        public void append(BehaviorDecision decision) {
            rows.add(0, decision);
        }

        @Override
        public List<BehaviorDecision> findLatest(String robotId, int limit) {
            synchronized (rows) {
                return rows.stream().filter(d -> d.robotId().equals(robotId)).limit(limit).toList();
            }
        }

        @Override
        public void trim(String robotId, int keep) {
            synchronized (rows) {
                while (rows.size() > keep) {
                    rows.remove(rows.size() - 1);
                }
            }
        }
    }

    private static final class InMemoryLeases implements LeasePort {

        private final Map<String, Lease> rows = new ConcurrentHashMap<>();

        @Override
        public synchronized boolean acquire(String key, String owner, Duration ttl) {
            var now = Instant.now();
            var current = rows.get(key);
            if (current == null || current.owner().equals(owner) || !current.expiresAt().isAfter(now)) {
                rows.put(key, new Lease(key, owner, now.plus(ttl)));
                return true;
            }
            return false;
        }

        @Override
        public synchronized void release(String key, String owner) {
            var current = rows.get(key);
            if (current != null && current.owner().equals(owner)) {
                rows.remove(key);
            }
        }

        @Override
        public Optional<Lease> holder(String key) {
            var now = Instant.now();
            return Optional.ofNullable(rows.get(key)).filter(l -> l.expiresAt().isAfter(now));
        }

        synchronized void force(String key, String owner) {
            rows.put(key, new Lease(key, owner, Instant.now().plus(Duration.ofMinutes(1))));
        }
    }
}

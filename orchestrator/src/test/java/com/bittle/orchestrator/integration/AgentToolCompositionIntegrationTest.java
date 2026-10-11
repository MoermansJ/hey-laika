package com.bittle.orchestrator.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.adapter.out.persistence.BehaviorRunLogJpaRepository;
import com.bittle.orchestrator.adapter.out.persistence.BehaviorRunLogRepositoryAdapter;
import com.bittle.orchestrator.adapter.out.persistence.LearnedPatternJpaRepository;
import com.bittle.orchestrator.adapter.out.persistence.LearnedPatternRepositoryAdapter;
import com.bittle.orchestrator.application.port.out.AdapterErrorException;
import com.bittle.orchestrator.application.port.out.AgentMetricsPort;
import com.bittle.orchestrator.application.port.out.ArbiterPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.application.service.AgentBehaviorService;
import com.bittle.orchestrator.application.service.GoalOutcomeEvaluator;
import com.bittle.orchestrator.application.service.LearnedPatternQueries;
import com.bittle.orchestrator.application.service.PatternRollupService;
import com.bittle.orchestrator.application.service.SensorStateService;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import com.bittle.orchestrator.domain.behavior.outcome.BarkChecker;
import com.bittle.orchestrator.domain.behavior.outcome.MoveForwardChecker;
import com.bittle.orchestrator.domain.behavior.outcome.OutcomeThresholds;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

/**
 * AGENT-17: the agent tool-composition lifecycle end to end — submission →
 * arbiter → completion polling → sensor-based outcome evaluation → pattern
 * rollup → pattern query — with the real services and JPA repositories (H2),
 * a scripted arbiter and a scripted robot adapter (odometry and audio).
 */
@DataJpaTest
class AgentToolCompositionIntegrationTest {

    private static final Instant T0 = Instant.parse("2026-10-11T22:00:00Z");
    private static final String ROBOT = "bittle-1";

    @Autowired
    private BehaviorRunLogJpaRepository runLogJpa;

    @Autowired
    private LearnedPatternJpaRepository patternJpa;

    private final StepClock clock = new StepClock(T0);
    private final ScriptedArbiter arbiter = new ScriptedArbiter();
    private final ScriptedRobot robot = new ScriptedRobot();
    private final AgentMetricsPort metrics = mock(AgentMetricsPort.class);
    private final RobotModeRepositoryPort modes = mock(RobotModeRepositoryPort.class);

    private BehaviorRunLogRepositoryAdapter runLogs;
    private AgentBehaviorService agent;
    private LearnedPatternQueries queries;

    @BeforeEach
    void setUp() {
        var mapper = new ObjectMapper();
        runLogs = new BehaviorRunLogRepositoryAdapter(runLogJpa, mapper);
        var patterns = new LearnedPatternRepositoryAdapter(patternJpa, mapper);
        var fleet = new Fleet(List.of(new Robot(ROBOT, "Laika", "bittle_x_v2", "http://laika")));
        var sensors = new SensorStateService(fleet, robot.port(), clock, Duration.ofMinutes(10));
        var thresholds = OutcomeThresholds.defaults();
        var evaluator = new GoalOutcomeEvaluator(List.of(new MoveForwardChecker(thresholds),
                new BarkChecker(thresholds)), clock);
        var rollups = new PatternRollupService(runLogs, patterns, clock);
        agent = new AgentBehaviorService(arbiter, runLogs, sensors, evaluator, rollups, metrics,
                modes, clock, 20, Duration.ofMinutes(10));
        queries = new LearnedPatternQueries(patterns, fleet, clock, Duration.ofSeconds(5));
        mode(OperatingMode.ROAMING);
    }

    @Test
    void givenSuccessfulMove_whenSubmittedAndCompleted_thenOutcomeAndPatternAreStored() {
        var response = agent.submitToolCall(ROBOT, "move_forward", "move_forward",
                UUID.randomUUID());
        assertThat(response.isAccepted()).isTrue();
        var stored = runLogs.findById(response.runLogId()).orElseThrow();
        assertThat(stored.goal()).isEqualTo("move_forward");
        assertThat(stored.completedAt()).isNull();

        robot.walkTo(0.12);                                   // 12 cm forward
        tick(3);
        arbiter.complete(response.runLogId(), clock.instant());
        assertThat(agent.pollAndEvaluateCompletions()).isEqualTo(1);

        var finished = runLogs.findById(response.runLogId()).orElseThrow();
        assertThat(finished.completedAt()).isNotNull();
        assertThat(finished.outcome().success()).isTrue();
        assertThat(finished.outcome().reason()).contains("12.0 cm");
        assertThat(arbiter.synced).containsKey(response.runLogId());
        assertThat(arbiter.synced.get(response.runLogId()).success()).isTrue();

        List<LearnedPattern> learned = queries.activePatterns(ROBOT, "move_forward");
        assertThat(learned).singleElement().satisfies(p -> {
            assertThat(p.toolCombination()).containsExactly("move_forward");
            assertThat(p.attempts()).isEqualTo(1);
            assertThat(p.successRate()).isEqualTo(1.0);
        });
        assertThat(agent.pollAndEvaluateCompletions()).isZero();       // nothing left pending
    }

    @Test
    void givenSeveralCombinations_whenRolledUp_thenEachHasItsOwnRateBestFirst() {
        // Decision A twice: move_forward alone, robot barely moves -> failure.
        for (int i = 0; i < 2; i++) {
            var run = agent.submitToolCall(ROBOT, "move_forward", "move_forward",
                    UUID.randomUUID()).runLogId();
            robot.walkBy(0.01);
            tick(2);
            arbiter.complete(run, clock.instant());
            agent.pollAndEvaluateCompletions();
            tick(1);
        }
        // Decision B twice: turn_left then move_forward under one decision -> success.
        for (int i = 0; i < 2; i++) {
            var decision = UUID.randomUUID();
            var turn = agent.submitToolCall(ROBOT, "turn_left", "move_forward", decision)
                    .runLogId();
            tick(1);
            var move = agent.submitToolCall(ROBOT, "move_forward", "move_forward", decision)
                    .runLogId();
            robot.walkBy(0.10);
            tick(2);
            arbiter.complete(turn, clock.instant());
            arbiter.complete(move, clock.instant());
            assertThat(agent.pollAndEvaluateCompletions()).isEqualTo(2);
            tick(1);
        }

        clock.advance(Duration.ofSeconds(10));                    // past the query cache
        var learned = queries.activePatterns(ROBOT, "move_forward");

        assertThat(learned).hasSize(2);
        assertThat(learned.get(0).toolCombination()).containsExactly("turn_left", "move_forward");
        assertThat(learned.get(0).attempts()).isEqualTo(2);
        assertThat(learned.get(0).successRate()).isEqualTo(1.0);
        assertThat(learned.get(1).toolCombination()).containsExactly("move_forward");
        assertThat(learned.get(1).attempts()).isEqualTo(2);
        assertThat(learned.get(1).successRate()).isZero();
    }

    @Test
    void givenStationaryMode_whenWalkingToolSubmitted_thenNothingReachesTheArbiterOrTheLog() {
        mode(OperatingMode.STATIONARY);

        var response = agent.submitToolCall(ROBOT, "move_forward", "move_forward",
                UUID.randomUUID());

        assertThat(response.status()).isEqualTo(ArbiterSubmissionResponse.REJECTED);
        assertThat(response.message()).contains("stationary");
        assertThat(arbiter.submissions).isEmpty();
        assertThat(runLogJpa.count()).isZero();

        var bark = agent.submitToolCall(ROBOT, "bark", "bark", UUID.randomUUID());
        assertThat(bark.isAccepted()).isTrue();
        assertThat(arbiter.submissions).extracting(ArbiterSubmissionRequest::behaviorName)
                .containsExactly("bark");
    }

    @Test
    void givenArbiterDown_whenSubmitted_thenRejectedAndNothingIsLogged() {
        arbiter.down = true;

        var response = agent.submitToolCall(ROBOT, "move_forward", "move_forward",
                UUID.randomUUID());

        assertThat(response.isAccepted()).isFalse();
        assertThat(response.message()).contains("Connection error");
        assertThat(runLogJpa.count()).isZero();
    }

    @Test
    void givenSensorsMissing_whenRunCompletes_thenOutcomeUndeterminedAndNotCountedAsAttempt() {
        robot.sensesDown = true;
        var run = agent.submitToolCall(ROBOT, "move_forward", "move_forward", UUID.randomUUID())
                .runLogId();
        tick(2);
        arbiter.complete(run, clock.instant());

        assertThat(agent.pollAndEvaluateCompletions()).isEqualTo(1);

        var finished = runLogs.findById(run).orElseThrow();
        assertThat(finished.outcome().success()).isNull();
        assertThat(finished.outcome().reason()).contains("odometry");
        assertThat(queries.activePatterns(ROBOT, "move_forward")).isEmpty();
    }

    @Test
    void givenPreemptedRun_whenPolled_thenUndeterminedAndSyncFailureDoesNotLoseTheOutcome() {
        arbiter.syncWorks = false;
        var run = agent.submitToolCall(ROBOT, "bark", "bark", UUID.randomUUID()).runLogId();
        tick(1);
        arbiter.preempt(run, clock.instant(), "safety-run");

        assertThat(agent.pollAndEvaluateCompletions()).isEqualTo(1);

        var finished = runLogs.findById(run).orElseThrow();
        assertThat(finished.preemptedBy()).isEqualTo("safety-run");
        assertThat(finished.outcome().success()).isNull();
        assertThat(finished.outcome().reason()).contains("preempted");
    }

    @Test
    void givenRunNeverFinishes_whenStale_thenClosedSoPollingStops() {
        var run = agent.submitToolCall(ROBOT, "bark", "bark", UUID.randomUUID()).runLogId();
        tick(5);
        assertThat(agent.pollAndEvaluateCompletions()).isZero();

        clock.advance(Duration.ofMinutes(11));
        assertThat(agent.pollAndEvaluateCompletions()).isEqualTo(1);

        assertThat(runLogs.findById(run).orElseThrow().outcome().reason())
                .contains("after 10 min");
        assertThat(runLogs.findPendingBySource("agent", 10)).isEmpty();
    }

    private void mode(OperatingMode mode) {
        when(modes.find(ROBOT)).thenReturn(Optional.of(new RobotMode(ROBOT, mode, T0, "test")));
    }

    private void tick(int seconds) {
        clock.advance(Duration.ofSeconds(seconds));
    }

    /** The adapter's arbiter: accepts unless down, runs finish when the test says so. */
    private static final class ScriptedArbiter implements ArbiterPort {
        final List<ArbiterSubmissionRequest> submissions = new ArrayList<>();
        final Map<UUID, BehaviorRunLog> runs = new LinkedHashMap<>();
        final Map<UUID, OutcomeEvaluation> synced = new LinkedHashMap<>();
        boolean down;
        boolean syncWorks = true;

        @Override
        public ArbiterSubmissionResponse submit(String robotId, ArbiterSubmissionRequest request) {
            if (down) {
                return ArbiterSubmissionResponse.rejected("Connection error: refused");
            }
            submissions.add(request);
            UUID id = UUID.randomUUID();
            runs.put(id, null);
            return new ArbiterSubmissionResponse(id, ArbiterSubmissionResponse.QUEUED, null,
                    submissions.size() - 1);
        }

        void complete(UUID id, Instant at) {
            runs.put(id, run(id, at, null));
        }

        void preempt(UUID id, Instant at, String by) {
            runs.put(id, run(id, at, by));
        }

        private static BehaviorRunLog run(UUID id, Instant completedAt, String preemptedBy) {
            return new BehaviorRunLog(id, ROBOT, completedAt.minusSeconds(1), completedAt,
                    "tool", "agent", 3, Map.of("type", "agent"), 1000L, preemptedBy, null, null,
                    null, null, null);
        }

        @Override
        public Optional<BehaviorRunLog> getRunLog(String robotId, UUID runLogId) {
            return Optional.ofNullable(runs.get(runLogId));
        }

        @Override
        public boolean syncOutcome(String robotId, UUID runLogId, OutcomeEvaluation outcome) {
            if (syncWorks) {
                synced.put(runLogId, outcome);
            }
            return syncWorks;
        }
    }

    /** The robot's adapter as SensorStateService reads it: pose (metres) and ears. */
    private static final class ScriptedRobot {
        private double xMetres;
        boolean sensesDown;
        private final RobotAdapterPort port = mock(RobotAdapterPort.class);

        ScriptedRobot() {
            when(port.get(any(), eq("/senses"))).thenAnswer(call -> {
                if (sensesDown) {
                    throw new AdapterErrorException(503, "{}");
                }
                return Map.of("pose", Map.of("x", xMetres, "y", 0.0, "heading", 0.0));
            });
            when(port.get(any(), eq("/ears"))).thenReturn(Map.of("level",
                    Map.of("peak", 16384)));
            when(port.getBinary(any(), eq("/eyes/snap")))
                    .thenThrow(new AdapterErrorException(404, "{\"error\":\"no_frame\"}"));
        }

        RobotAdapterPort port() {
            return port;
        }

        void walkTo(double x) {
            xMetres = x;
        }

        void walkBy(double dx) {
            xMetres += dx;
        }
    }

    private static final class StepClock extends Clock {
        private Instant now;

        StepClock(Instant start) {
            now = start;
        }

        void advance(Duration step) {
            now = now.plus(step);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return now;
        }
    }
}

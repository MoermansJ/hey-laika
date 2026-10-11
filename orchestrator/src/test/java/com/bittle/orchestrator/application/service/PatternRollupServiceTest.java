package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.BehaviorRunLogRepositoryPort;
import com.bittle.orchestrator.application.port.out.LearnedPatternRepositoryPort;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.bittle.orchestrator.domain.behavior.PatternStatus;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class PatternRollupServiceTest {

    private static final Instant T0 = Instant.parse("2026-10-11T20:00:00Z");
    private static final Instant NOW = Instant.parse("2026-10-11T21:40:00Z");
    private static final String GOAL = "look_upward";

    private final BehaviorRunLogRepositoryPort runLogs = mock(BehaviorRunLogRepositoryPort.class);
    private final InMemoryPatterns patterns = new InMemoryPatterns();
    private final PatternRollupService service = new PatternRollupService(runLogs, patterns,
            Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void givenSingleToolRuns_whenRolledUp_thenStatsPerToolAreComputed() {
        runs(run("look_up", "d1", 0, true), run("look_up", "d2", 10, true),
                run("look_up", "d3", 20, false), run("tilt_head", "d4", 30, false));

        var result = service.rollupPatternsForGoal("bittle-1", GOAL);

        assertThat(result).hasSize(2);
        var lookUp = result.get(0);
        assertThat(lookUp.toolCombination()).containsExactly("look_up");
        assertThat(lookUp.attempts()).isEqualTo(3);
        assertThat(lookUp.successes()).isEqualTo(2);
        assertThat(lookUp.successRate()).isEqualTo(2.0 / 3.0);
        assertThat(lookUp.lastUsed()).isEqualTo(T0.plusSeconds(20));
        assertThat(lookUp.status()).isEqualTo(PatternStatus.ACTIVE);
        assertThat(lookUp.updatedAt()).isEqualTo(NOW);
        var tilt = result.get(1);
        assertThat(tilt.toolCombination()).containsExactly("tilt_head");
        assertThat(tilt.successRate()).isZero();
        assertThat(patterns.all()).hasSize(2);
    }

    @Test
    void givenRunsSharingADecision_whenRolledUp_thenTheyFormOneOrderedCombination() {
        runs(run("lower_left_paw", "d1", 1, true), run("raise_right_paw", "d1", 0, false),
                run("raise_right_paw", "d2", 10, false), run("lower_left_paw", "d2", 11, false));

        var result = service.rollupPatternsForGoal("bittle-1", GOAL);

        assertThat(result).singleElement().satisfies(p -> {
            assertThat(p.toolCombination()).containsExactly("raise_right_paw", "lower_left_paw");
            assertThat(p.attempts()).isEqualTo(2);
            assertThat(p.successes()).isEqualTo(1);
            assertThat(p.successRate()).isEqualTo(0.5);
        });
    }

    @Test
    void givenUndeterminedFinalOutcome_whenRolledUp_thenThatAttemptIsNotCounted() {
        runs(run("look_up", "d1", 0, true), run("look_up", "d2", 10, null));

        var result = service.rollupPatternsForGoal("bittle-1", GOAL);

        assertThat(result).singleElement().satisfies(p -> {
            assertThat(p.attempts()).isEqualTo(1);
            assertThat(p.successes()).isEqualTo(1);
        });
    }

    @Test
    void givenNonAgentRunsAndRunsWithoutDecision_whenRolledUp_thenOnlyAgentRunsCountEachAlone() {
        var manual = new BehaviorRunLog(UUID.randomUUID(), "bittle-1", T0, T0.plusSeconds(1),
                "look_up", "manual", 2, null, 1000L, null, GOAL, outcome(true), null, T0, T0);
        runs(manual, run("look_up", null, 5, true), run("look_up", null, 6, false));

        var result = service.rollupPatternsForGoal("bittle-1", GOAL);

        assertThat(result).singleElement().satisfies(p -> {
            assertThat(p.attempts()).isEqualTo(2);
            assertThat(p.successes()).isEqualTo(1);
        });
    }

    @Test
    void givenExistingPattern_whenRolledUpAgain_thenItIsUpdatedInPlace() {
        runs(run("look_up", "d1", 0, false));
        var first = service.rollupPatternsForGoal("bittle-1", GOAL).get(0);
        runs(run("look_up", "d1", 0, false), run("look_up", "d2", 10, true));

        var second = service.rollupPatternsForGoal("bittle-1", GOAL).get(0);

        assertThat(second.id()).isEqualTo(first.id());
        assertThat(second.firstDiscovered()).isEqualTo(first.firstDiscovered());
        assertThat(second.attempts()).isEqualTo(2);
        assertThat(second.successRate()).isEqualTo(0.5);
        assertThat(patterns.all()).hasSize(1);
    }

    @Test
    void givenCombinationThatDisappeared_whenRolledUp_thenItIsResetAndInactive() {
        runs(run("raise_right_paw", "d1", 0, true));
        service.rollupPatternsForGoal("bittle-1", GOAL);
        runs(run("raise_right_paw", "d1", 0, false), run("lower_left_paw", "d1", 1, true));

        var result = service.rollupPatternsForGoal("bittle-1", GOAL);

        assertThat(result).singleElement().satisfies(p ->
                assertThat(p.toolCombination()).containsExactly("raise_right_paw",
                        "lower_left_paw"));
        var retired = patterns.all().stream()
                .filter(p -> p.toolCombination().equals(List.of("raise_right_paw")))
                .findFirst().orElseThrow();
        assertThat(retired.status()).isEqualTo(PatternStatus.INACTIVE);
        assertThat(retired.attempts()).isZero();
    }

    @Test
    void givenNoRunsOrNoGoal_whenRolledUp_thenNothingIsSaved() {
        runs();

        assertThat(service.rollupPatternsForGoal("bittle-1", GOAL)).isEmpty();
        assertThat(service.rollupPatternsForGoal("bittle-1", null)).isEmpty();
        assertThat(patterns.all()).isEmpty();
    }

    @Test
    void givenEqualRates_whenRolledUp_thenMoreAttemptsComeFirst() {
        runs(run("a", "d1", 0, true), run("b", "d2", 1, true), run("b", "d3", 2, true));

        var result = service.rollupPatternsForGoal("bittle-1", GOAL);

        assertThat(result).extracting(p -> p.toolCombination().get(0)).containsExactly("b", "a");
    }

    @Test
    void givenManyRuns_whenRolledUp_thenItStaysFast() {
        var many = new ArrayList<BehaviorRunLog>();
        for (int i = 0; i < 500; i++) {
            many.add(run(i % 2 == 0 ? "look_up" : "tilt_head", "d" + i, i, i % 3 == 0));
        }
        runs(many.toArray(BehaviorRunLog[]::new));
        service.rollupPatternsForGoal("bittle-1", GOAL); // warm-up

        long start = System.nanoTime();
        service.rollupPatternsForGoal("bittle-1", GOAL);
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        // Design target is < 2 ms per goal; leave headroom for slow CI machines.
        assertThat(elapsedMs).isLessThan(200);
    }

    private void runs(BehaviorRunLog... runs) {
        when(runLogs.findByRobotIdAndGoalWithOutcome("bittle-1", GOAL)).thenReturn(List.of(runs));
    }

    private static BehaviorRunLog run(String tool, String decisionId, int secondsAfterT0,
                                      Boolean success) {
        Map<String, Object> cause = new LinkedHashMap<>();
        cause.put("type", "agent");
        cause.put("decisionId", decisionId);
        Instant at = T0.plusSeconds(secondsAfterT0);
        return new BehaviorRunLog(UUID.randomUUID(), "bittle-1", at, at.plusSeconds(1), tool,
                "agent", 3, cause, 1000L, null, GOAL, outcome(success), null, at, at);
    }

    private static OutcomeEvaluation outcome(Boolean success) {
        return new OutcomeEvaluation(success, success == null ? 0.0 : 0.8, "test", "1.0", NOW);
    }

    private static final class InMemoryPatterns implements LearnedPatternRepositoryPort {
        private final Map<UUID, LearnedPattern> byId = new LinkedHashMap<>();

        List<LearnedPattern> all() {
            return new ArrayList<>(byId.values());
        }

        @Override
        public LearnedPattern save(LearnedPattern pattern) {
            byId.put(pattern.id(), pattern);
            return pattern;
        }

        @Override
        public Optional<LearnedPattern> findById(UUID id) {
            return Optional.ofNullable(byId.get(id));
        }

        @Override
        public List<LearnedPattern> findByRobotIdAndGoal(String robotId, String goal) {
            return byId.values().stream()
                    .filter(p -> p.robotId().equals(robotId) && p.goal().equals(goal)).toList();
        }

        @Override
        public List<LearnedPattern> findByRobotIdAndGoalOrderBySuccessRateDesc(String robotId,
                                                                               String goal) {
            return findByRobotIdAndGoal(robotId, goal).stream()
                    .sorted(Comparator.comparingDouble(LearnedPattern::successRate).reversed())
                    .toList();
        }

        @Override
        public List<LearnedPattern> findByRobotIdAndStatus(String robotId, PatternStatus status) {
            return byId.values().stream()
                    .filter(p -> p.robotId().equals(robotId) && p.status() == status).toList();
        }

        @Override
        public Optional<LearnedPattern> findByRobotIdAndGoalAndToolCombination(
                String robotId, String goal, List<String> toolCombination) {
            return findByRobotIdAndGoal(robotId, goal).stream()
                    .filter(p -> p.toolCombination().equals(toolCombination)).findFirst();
        }
    }
}

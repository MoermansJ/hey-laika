package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.outcome.GoalCheck;
import com.bittle.orchestrator.domain.behavior.outcome.GoalOutcomeChecker;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.BiFunction;
import org.junit.jupiter.api.Test;

class GoalOutcomeEvaluatorTest {

    private static final Instant NOW = Instant.parse("2026-10-11T21:30:00Z");
    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);
    private static final SensorSnapshot BEFORE = new SensorSnapshot(NOW.minusSeconds(2), null,
            new SensorSnapshot.Odometry(0, 0, 0), 0.1, null);
    private static final SensorSnapshot AFTER = new SensorSnapshot(NOW, null,
            new SensorSnapshot.Odometry(12, 0, 0), 0.5, null);

    @Test
    void givenRegisteredGoal_whenEvaluated_thenCheckerResultIsStampedWithVersionAndTime() {
        var evaluator = new GoalOutcomeEvaluator(List.of(
                checker("move_forward", (b, a) -> GoalCheck.succeeded(0.6, "moved 12.0 cm"))),
                CLOCK);

        var outcome = evaluator.evaluateOutcome(run("move_forward"), BEFORE, AFTER);

        assertThat(outcome.success()).isTrue();
        assertThat(outcome.confidence()).isEqualTo(0.6);
        assertThat(outcome.reason()).isEqualTo("moved 12.0 cm");
        assertThat(outcome.evaluatorVersion()).isEqualTo(GoalOutcomeEvaluator.EVALUATOR_VERSION);
        assertThat(outcome.evaluatedAt()).isEqualTo(NOW);
    }

    @Test
    void givenSeveralCheckers_whenEvaluated_thenTheGoalSelectsTheChecker() {
        var evaluator = new GoalOutcomeEvaluator(List.of(
                checker("bark", (b, a) -> GoalCheck.failed(0.9, "silent")),
                checker("move_forward", (b, a) -> GoalCheck.succeeded(1.0, "moved"))), CLOCK);

        assertThat(evaluator.evaluateOutcome(run("bark"), BEFORE, AFTER).success()).isFalse();
        assertThat(evaluator.evaluateOutcome(run("move_forward"), BEFORE, AFTER).success())
                .isTrue();
        assertThat(evaluator.registeredGoals()).containsExactly("bark", "move_forward");
        assertThat(evaluator.supports("bark")).isTrue();
        assertThat(evaluator.supports("fly")).isFalse();
        assertThat(evaluator.supports(null)).isFalse();
    }

    @Test
    void givenCheckerSeesBothSnapshots_whenEvaluated_thenItGetsThemInOrder() {
        var evaluator = new GoalOutcomeEvaluator(List.of(checker("move_forward", (b, a) ->
                GoalCheck.succeeded(1.0, (a.odometryPosition().xCm() - b.odometryPosition().xCm())
                        + " cm"))), CLOCK);

        assertThat(evaluator.evaluateOutcome(run("move_forward"), BEFORE, AFTER).reason())
                .isEqualTo("12.0 cm");
    }

    @Test
    void givenUnregisteredGoal_whenEvaluated_thenUndeterminedFallback() {
        var evaluator = new GoalOutcomeEvaluator(List.of(), CLOCK);

        var outcome = evaluator.evaluateOutcome(run("look_upward"), BEFORE, AFTER);

        assertThat(outcome.success()).isNull();
        assertThat(outcome.confidence()).isZero();
        assertThat(outcome.reason()).isEqualTo("No evaluator registered for goal: look_upward");
        assertThat(outcome.evaluatorVersion()).isEqualTo("1.0");
        assertThat(outcome.evaluatedAt()).isEqualTo(NOW);
    }

    @Test
    void givenNoGoal_whenEvaluated_thenUndetermined() {
        var evaluator = new GoalOutcomeEvaluator(List.of(), CLOCK);

        var outcome = evaluator.evaluateOutcome(run(null), BEFORE, AFTER);

        assertThat(outcome.success()).isNull();
        assertThat(outcome.reason()).isEqualTo("No goal declared");
    }

    @Test
    void givenMissingSnapshot_whenEvaluated_thenUndeterminedWithoutCallingTheChecker() {
        var evaluator = new GoalOutcomeEvaluator(List.of(checker("bark", (b, a) -> {
            throw new AssertionError("checker must not run");
        })), CLOCK);

        var outcome = evaluator.evaluateOutcome(run("bark"), null, AFTER);

        assertThat(outcome.success()).isNull();
        assertThat(outcome.reason()).contains("before");
    }

    @Test
    void givenThrowingChecker_whenEvaluated_thenUndeterminedInsteadOfException() {
        var evaluator = new GoalOutcomeEvaluator(List.of(checker("bark", (b, a) -> {
            throw new IllegalStateException("no audio");
        })), CLOCK);

        var outcome = evaluator.evaluateOutcome(run("bark"), BEFORE, AFTER);

        assertThat(outcome.success()).isNull();
        assertThat(outcome.confidence()).isZero();
        assertThat(outcome.reason()).isEqualTo("Evaluator failed: no audio");
    }

    @Test
    void givenCheckerReturningNull_whenEvaluated_thenUndetermined() {
        var evaluator = new GoalOutcomeEvaluator(List.of(checker("bark", (b, a) -> null)), CLOCK);

        assertThat(evaluator.evaluateOutcome(run("bark"), BEFORE, AFTER).success()).isNull();
    }

    @Test
    void givenOutOfRangeConfidence_whenEvaluated_thenItIsClampedIntoTheValidRange() {
        var evaluator = new GoalOutcomeEvaluator(List.of(
                checker("bark", (b, a) -> GoalCheck.succeeded(3.5, "loud"))), CLOCK);

        assertThat(evaluator.evaluateOutcome(run("bark"), BEFORE, AFTER).confidence())
                .isEqualTo(1.0);
    }

    @Test
    void givenTwoCheckersForOneGoal_whenRegistered_thenRejected() {
        var first = checker("bark", (b, a) -> GoalCheck.undetermined(""));
        var second = checker("bark", (b, a) -> GoalCheck.undetermined(""));

        assertThatThrownBy(() -> new GoalOutcomeEvaluator(List.of(first, second), CLOCK))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("bark");
    }

    private static BehaviorRunLog run(String goal) {
        return new BehaviorRunLog(UUID.randomUUID(), "bittle-1", NOW.minusSeconds(2), NOW,
                "some_tool", "agent", 3, Map.of("type", "agent"), 2000L, null, goal, null, null,
                NOW.minusSeconds(2), NOW);
    }

    private static GoalOutcomeChecker checker(String goal,
                                              BiFunction<SensorSnapshot, SensorSnapshot,
                                                      GoalCheck> body) {
        return new GoalOutcomeChecker() {
            @Override
            public String goal() {
                return goal;
            }

            @Override
            public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
                return body.apply(before, after);
            }
        };
    }
}

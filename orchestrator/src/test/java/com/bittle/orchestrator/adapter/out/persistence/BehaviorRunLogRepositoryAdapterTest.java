package com.bittle.orchestrator.adapter.out.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class BehaviorRunLogRepositoryAdapterTest {

    private static final Instant T0 = Instant.parse("2026-10-11T12:00:00Z");
    private static final Instant NOW = Instant.parse("2026-10-11T13:00:00Z");

    @Autowired
    private BehaviorRunLogJpaRepository jpa;

    private BehaviorRunLogRepositoryAdapter runLogs;

    @BeforeEach
    void setUp() {
        runLogs = new BehaviorRunLogRepositoryAdapter(jpa, new ObjectMapper(),
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private static BehaviorRunLog run(String robotId, String source, String goal, Instant at) {
        return new BehaviorRunLog(UUID.randomUUID(), robotId, at, null, "raise_right_paw", source,
                "agent".equals(source) ? 3 : 2,
                "agent".equals(source) ? Map.of("type", "agent", "decisionId", "d-1") : null,
                null, null, goal, null, null, null, null);
    }

    private static OutcomeEvaluation outcome(boolean success) {
        return new OutcomeEvaluation(success, 0.8, "pitch changed", "v1", T0.plusSeconds(30));
    }

    @Test
    void givenNonAgentRun_whenSavedAndRead_thenOutcomeIsNullAndFieldsRoundTrip() {
        var saved = runLogs.save(run("bittle-1", "manual", null, T0));

        var read = runLogs.findById(saved.id()).orElseThrow();

        assertThat(read.outcome()).isNull();
        assertThat(read.goal()).isNull();
        assertThat(read.cause()).isNull();
        assertThat(read.robotId()).isEqualTo("bittle-1");
        assertThat(read.timestamp()).isEqualTo(T0);
        assertThat(read.source()).isEqualTo("manual");
        assertThat(read.createdAt()).isEqualTo(NOW);
    }

    @Test
    void givenRowWrittenWithoutOutcomeColumns_whenRead_thenItIsReadableWithNullOutcome() {
        // A row as written before outcome evaluation existed: only the base columns set.
        var legacy = new BehaviorRunLogEntity();
        legacy.setId(UUID.randomUUID());
        legacy.setRobotId("bittle-1");
        legacy.setRunTimestamp(T0);
        legacy.setBehaviorName("sit");
        legacy.setSource("lifecycle");
        jpa.saveAndFlush(legacy);

        var read = runLogs.findById(legacy.getId()).orElseThrow();

        assertThat(read.behaviorName()).isEqualTo("sit");
        assertThat(read.outcome()).isNull();
        assertThat(read.sensorDelta()).isNull();
    }

    @Test
    void givenAgentRun_whenOutcomeAttached_thenItIsQueryableByGoal() {
        var saved = runLogs.save(run("bittle-1", "agent", "look_upward", T0));
        assertThat(runLogs.findByRobotIdAndGoalWithOutcome("bittle-1", "look_upward")).isEmpty();

        var updated = runLogs.attachOutcome(saved.id(), outcome(true)).orElseThrow();

        assertThat(updated.outcome()).isEqualTo(outcome(true));
        assertThat(updated.updatedAt()).isEqualTo(NOW);
        var byGoal = runLogs.findByRobotIdAndGoalWithOutcome("bittle-1", "look_upward");
        assertThat(byGoal).singleElement().satisfies(r -> {
            assertThat(r.id()).isEqualTo(saved.id());
            assertThat(r.outcome().success()).isTrue();
            assertThat(r.outcome().confidence()).isEqualTo(0.8);
            assertThat(r.outcome().reason()).isEqualTo("pitch changed");
            assertThat(r.outcome().evaluatorVersion()).isEqualTo("v1");
            assertThat(r.outcome().evaluatedAt()).isEqualTo(T0.plusSeconds(30));
            assertThat(r.cause()).containsEntry("type", "agent").containsEntry("decisionId", "d-1");
        });
    }

    @Test
    void givenMixedRuns_whenQueryingByGoalWithOutcome_thenOnlyEvaluatedRunsOfThatRobotAndGoalNewestFirst() {
        var older = runLogs.save(run("bittle-1", "agent", "look_upward", T0));
        var newer = runLogs.save(run("bittle-1", "agent", "look_upward", T0.plusSeconds(60)));
        var unevaluated = runLogs.save(run("bittle-1", "agent", "look_upward", T0.plusSeconds(120)));
        var otherGoal = runLogs.save(run("bittle-1", "agent", "sit_down", T0));
        var otherRobot = runLogs.save(run("bittle-2", "agent", "look_upward", T0));
        runLogs.attachOutcome(older.id(), outcome(false));
        runLogs.attachOutcome(newer.id(), outcome(true));
        runLogs.attachOutcome(otherGoal.id(), outcome(true));
        runLogs.attachOutcome(otherRobot.id(), outcome(true));

        var result = runLogs.findByRobotIdAndGoalWithOutcome("bittle-1", "look_upward");

        assertThat(result).extracting(BehaviorRunLog::id).containsExactly(newer.id(), older.id());
        assertThat(result).extracting(BehaviorRunLog::id).doesNotContain(unevaluated.id());
    }

    @Test
    void givenMixedSources_whenQueryingBySourceWithOutcome_thenOnlyEvaluatedRunsOfThatSource() {
        var agent = runLogs.save(run("bittle-1", "agent", "look_upward", T0));
        var agentPending = runLogs.save(run("bittle-1", "agent", "look_upward", T0.plusSeconds(5)));
        var manual = runLogs.save(run("bittle-1", "manual", null, T0));
        runLogs.attachOutcome(agent.id(), outcome(true));

        assertThat(runLogs.findByRobotIdAndSourceWithOutcome("bittle-1", "agent"))
                .extracting(BehaviorRunLog::id).containsExactly(agent.id());
        assertThat(runLogs.findByRobotIdAndSourceWithOutcome("bittle-1", "manual")).isEmpty();
        assertThat(runLogs.findByRobotIdAndSource("bittle-1", "agent"))
                .extracting(BehaviorRunLog::id).containsExactly(agentPending.id(), agent.id());
        assertThat(runLogs.findByRobotIdAndSource("bittle-1", "manual"))
                .extracting(BehaviorRunLog::id).containsExactly(manual.id());
    }

    @Test
    void givenJpaRepository_whenUsingDesignQueryMethods_thenOutcomeTaggedRowsAreReturned() {
        var evaluated = runLogs.save(run("bittle-1", "agent", "look_upward", T0));
        runLogs.save(run("bittle-1", "agent", "look_upward", T0.plusSeconds(1)));
        runLogs.attachOutcome(evaluated.id(), outcome(true));

        assertThat(jpa.findByRobotIdAndGoalAndOutcomeNotNull("bittle-1", "look_upward"))
                .extracting(BehaviorRunLogEntity::getId).containsExactly(evaluated.id());
        assertThat(jpa.findByRobotIdAndSourceAndOutcomeIsNotNull("bittle-1", "agent"))
                .extracting(BehaviorRunLogEntity::getId).containsExactly(evaluated.id());
    }

    @Test
    void givenUnknownId_whenAttachingOutcome_thenNothingIsWritten() {
        assertThat(runLogs.attachOutcome(UUID.randomUUID(), outcome(true))).isEmpty();
        assertThat(jpa.count()).isZero();
    }

    @Test
    void givenRunWithSensorDelta_whenSavedAndRead_thenDeltaRoundTrips() {
        var base = run("bittle-1", "agent", "look_upward", T0);
        var withDelta = new BehaviorRunLog(base.id(), base.robotId(), base.timestamp(), T0.plusSeconds(2),
                base.behaviorName(), base.source(), base.priority(), base.cause(), 2000L, null,
                base.goal(), outcome(true), Map.of("pitch", 12.5), null, null);

        var read = runLogs.findById(runLogs.save(withDelta).id()).orElseThrow();

        assertThat(read.sensorDelta()).containsEntry("pitch", 12.5);
        assertThat(read.executionTimeMs()).isEqualTo(2000L);
        assertThat(read.completedAt()).isEqualTo(T0.plusSeconds(2));
        assertThat(read.outcome()).isEqualTo(outcome(true));
    }

    @Test
    void givenMixedRuns_whenPendingQueried_thenOnlyUncompletedRunsOfTheSourceOldestFirst() {
        var older = runLogs.save(run("bittle-1", "agent", "look_upward", T0));
        var newer = runLogs.save(run("bittle-1", "agent", "bark", T0.plusSeconds(10)));
        var done = run("bittle-1", "agent", "bark", T0.plusSeconds(5));
        runLogs.save(new BehaviorRunLog(done.id(), done.robotId(), done.timestamp(),
                T0.plusSeconds(6), done.behaviorName(), done.source(), done.priority(),
                done.cause(), 1000L, null, done.goal(), null, null, null, null));
        runLogs.save(run("bittle-1", "manual", null, T0.plusSeconds(1)));

        assertThat(runLogs.findPendingBySource("agent", 10))
                .extracting(BehaviorRunLog::id)
                .containsExactly(older.id(), newer.id());
        assertThat(runLogs.findPendingBySource("agent", 1))
                .extracting(BehaviorRunLog::id)
                .containsExactly(older.id());
        assertThat(runLogs.findPendingBySource("agent", 0)).isEmpty();
    }
}

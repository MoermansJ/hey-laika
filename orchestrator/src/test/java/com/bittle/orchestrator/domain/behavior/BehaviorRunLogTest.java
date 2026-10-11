package com.bittle.orchestrator.domain.behavior;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class BehaviorRunLogTest {

    private static final Instant T0 = Instant.parse("2026-10-11T12:00:00Z");

    private static BehaviorRunLog run(String source, String goal, Map<String, Object> cause) {
        return new BehaviorRunLog(UUID.randomUUID(), "bittle-1", T0, null, "raise_right_paw",
                source, 3, cause, null, null, goal, null, null, T0, T0);
    }

    @Test
    void givenNonAgentRun_whenCreated_thenOutcomeAndGoalAreNull() {
        var run = run("manual", null, null);

        assertThat(run.outcome()).isNull();
        assertThat(run.goal()).isNull();
        assertThat(run.hasOutcome()).isFalse();
    }

    @Test
    void givenAgentRun_whenOutcomeAttached_thenCopyCarriesOutcomeAndOriginalIsUnchanged() {
        var run = run("agent", "look_upward", Map.of("type", "agent"));
        var outcome = new OutcomeEvaluation(true, 0.9, "pitch rose 12 deg", "v1", T0.plusSeconds(5));

        var evaluated = run.withOutcome(outcome, T0.plusSeconds(6));

        assertThat(evaluated.outcome()).isEqualTo(outcome);
        assertThat(evaluated.hasOutcome()).isTrue();
        assertThat(evaluated.updatedAt()).isEqualTo(T0.plusSeconds(6));
        assertThat(evaluated.id()).isEqualTo(run.id());
        assertThat(evaluated.goal()).isEqualTo("look_upward");
        assertThat(run.outcome()).isNull();
    }

    @Test
    void givenMutableCauseMap_whenRunCreated_thenLaterChangesDoNotLeakIn() {
        var cause = new HashMap<String, Object>();
        cause.put("type", "agent");
        cause.put("decisionId", null);

        var run = run("agent", "look_upward", cause);
        cause.put("type", "changed");

        assertThat(run.cause()).containsEntry("type", "agent").containsKey("decisionId");
        assertThatThrownBy(() -> run.cause().put("x", 1))
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void givenMissingId_whenCreated_thenRejected() {
        assertThatThrownBy(() -> new BehaviorRunLog(null, "bittle-1", T0, null, null, null, null,
                null, null, null, null, null, null, null, null))
                .isInstanceOf(NullPointerException.class);
    }

    @Test
    void givenConfidenceOutOfRange_whenOutcomeCreated_thenRejected() {
        assertThatThrownBy(() -> new OutcomeEvaluation(true, 1.5, "r", "v1", T0))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new OutcomeEvaluation(true, -0.1, "r", "v1", T0))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void givenUndecidedOutcome_whenCreated_thenSuccessAndConfidenceMayBeNull() {
        var outcome = new OutcomeEvaluation(null, null, "no sensor data", "v1", T0);

        assertThat(outcome.success()).isNull();
        assertThat(outcome.confidence()).isNull();
    }

    @Test
    void givenMissingEvaluatedAt_whenOutcomeCreated_thenRejected() {
        assertThatThrownBy(() -> new OutcomeEvaluation(true, 0.5, "r", "v1", null))
                .isInstanceOf(NullPointerException.class);
    }
}

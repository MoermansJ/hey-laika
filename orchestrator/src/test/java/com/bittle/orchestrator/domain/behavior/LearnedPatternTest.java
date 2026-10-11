package com.bittle.orchestrator.domain.behavior;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class LearnedPatternTest {

    private static final Instant T0 = Instant.parse("2026-10-11T12:00:00Z");

    @Test
    void givenNewCombination_whenDiscovered_thenItIsActiveWithZeroStats() {
        var pattern = LearnedPattern.discovered("bittle-1", "look_upward",
                List.of("raise_right_paw", "look_up"), T0);

        assertThat(pattern.id()).isNotNull();
        assertThat(pattern.attempts()).isZero();
        assertThat(pattern.successes()).isZero();
        assertThat(pattern.successRate()).isZero();
        assertThat(pattern.status()).isEqualTo(PatternStatus.ACTIVE);
        assertThat(pattern.firstDiscovered()).isEqualTo(T0);
        assertThat(pattern.lastUsed()).isNull();
        assertThat(pattern.createdAt()).isEqualTo(T0);
    }

    @Test
    void givenPattern_whenStatsUpdated_thenSuccessRateIsDerivedAndIdentityKept() {
        var pattern = LearnedPattern.discovered("bittle-1", "look_upward", List.of("look_up"), T0);

        var updated = pattern.withStats(4, 3, T0.plusSeconds(60), T0.plusSeconds(61));

        assertThat(updated.successRate()).isEqualTo(0.75);
        assertThat(updated.attempts()).isEqualTo(4);
        assertThat(updated.successes()).isEqualTo(3);
        assertThat(updated.lastUsed()).isEqualTo(T0.plusSeconds(60));
        assertThat(updated.updatedAt()).isEqualTo(T0.plusSeconds(61));
        assertThat(updated.id()).isEqualTo(pattern.id());
        assertThat(updated.firstDiscovered()).isEqualTo(T0);
        assertThat(pattern.attempts()).isZero();
    }

    @Test
    void givenZeroAttempts_whenRateComputed_thenItIsZeroNotNaN() {
        assertThat(LearnedPattern.rate(0, 0)).isZero();
        assertThat(LearnedPattern.rate(2, 1)).isEqualTo(0.5);
    }

    @Test
    void givenMutableCombination_whenPatternCreated_thenItKeepsAnImmutableCopy() {
        var tools = new ArrayList<>(List.of("sit", "look_up"));
        var pattern = LearnedPattern.discovered("bittle-1", "look_upward", tools, T0);

        tools.add("stand");

        assertThat(pattern.toolCombination()).containsExactly("sit", "look_up");
        assertThatThrownBy(() -> pattern.toolCombination().add("x"))
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void givenInvalidCounts_whenCreated_thenItIsRejected() {
        assertThatThrownBy(() -> new LearnedPattern(UUID.randomUUID(), "bittle-1", "g", List.of("sit"),
                1, 2, 2.0, T0, null, PatternStatus.ACTIVE, T0, T0))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new LearnedPattern(UUID.randomUUID(), "bittle-1", "g", List.of(),
                0, 0, 0.0, T0, null, PatternStatus.ACTIVE, T0, T0))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void givenStatusWireIds_whenParsed_thenTheyRoundTrip() {
        for (var status : PatternStatus.values()) {
            assertThat(PatternStatus.fromWireId(status.wireId())).isEqualTo(status);
        }
        assertThat(PatternStatus.DEPRECATED.wireId()).isEqualTo("deprecated");
        assertThatThrownBy(() -> PatternStatus.fromWireId("bogus"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void givenPattern_whenStatusChanged_thenOnlyStatusAndUpdatedAtChange() {
        var pattern = LearnedPattern.discovered("bittle-1", "look_upward", List.of("look_up"), T0)
                .withStats(2, 1, T0, T0);

        var deprecated = pattern.withStatus(PatternStatus.DEPRECATED, T0.plusSeconds(5));

        assertThat(deprecated.status()).isEqualTo(PatternStatus.DEPRECATED);
        assertThat(deprecated.updatedAt()).isEqualTo(T0.plusSeconds(5));
        assertThat(deprecated.successRate()).isEqualTo(0.5);
    }
}

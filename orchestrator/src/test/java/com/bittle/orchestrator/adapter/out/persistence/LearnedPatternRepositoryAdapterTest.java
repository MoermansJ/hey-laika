package com.bittle.orchestrator.adapter.out.persistence;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.PatternStatus;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;

@DataJpaTest
class LearnedPatternRepositoryAdapterTest {

    private static final Instant T0 = Instant.parse("2026-10-11T12:00:00Z");
    private static final Instant NOW = Instant.parse("2026-10-11T13:00:00Z");

    @Autowired
    private LearnedPatternJpaRepository jpa;

    private LearnedPatternRepositoryAdapter patterns;

    @BeforeEach
    void setUp() {
        patterns = new LearnedPatternRepositoryAdapter(jpa, new ObjectMapper(),
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private static LearnedPattern pattern(String robotId, String goal, List<String> tools,
                                          int attempts, int successes) {
        return LearnedPattern.discovered(robotId, goal, tools, T0)
                .withStats(attempts, successes, T0.plusSeconds(10), T0.plusSeconds(10));
    }

    @Test
    void givenPattern_whenSavedAndRead_thenAllFieldsRoundTrip() {
        var saved = patterns.save(pattern("bittle-1", "look_upward",
                List.of("raise_right_paw", "look_up"), 4, 3));

        var read = patterns.findById(saved.id()).orElseThrow();

        assertThat(read.robotId()).isEqualTo("bittle-1");
        assertThat(read.goal()).isEqualTo("look_upward");
        assertThat(read.toolCombination()).containsExactly("raise_right_paw", "look_up");
        assertThat(read.attempts()).isEqualTo(4);
        assertThat(read.successes()).isEqualTo(3);
        assertThat(read.successRate()).isEqualTo(0.75);
        assertThat(read.firstDiscovered()).isEqualTo(T0);
        assertThat(read.lastUsed()).isEqualTo(T0.plusSeconds(10));
        assertThat(read.status()).isEqualTo(PatternStatus.ACTIVE);
        assertThat(read.createdAt()).isEqualTo(T0);
        assertThat(read.updatedAt()).isEqualTo(T0.plusSeconds(10));
    }

    @Test
    void givenPatternWithoutTimestamps_whenSaved_thenCreatedAndUpdatedDefaultToClock() {
        var bare = new LearnedPattern(UUID.randomUUID(), "bittle-1", "sit_down", List.of("sit"),
                0, 0, 0.0, null, null, PatternStatus.ACTIVE, null, null);

        var read = patterns.findById(patterns.save(bare).id()).orElseThrow();

        assertThat(read.createdAt()).isEqualTo(NOW);
        assertThat(read.updatedAt()).isEqualTo(NOW);
    }

    @Test
    void givenSavedPattern_whenStatsUpdatedAndSavedAgain_thenTheSameRowIsUpdated() {
        var saved = patterns.save(pattern("bittle-1", "look_upward", List.of("look_up"), 1, 0));

        patterns.save(saved.withStats(2, 1, T0.plusSeconds(20), T0.plusSeconds(20)));

        assertThat(jpa.count()).isEqualTo(1);
        var read = patterns.findById(saved.id()).orElseThrow();
        assertThat(read.attempts()).isEqualTo(2);
        assertThat(read.successRate()).isEqualTo(0.5);
    }

    @Test
    void givenPatternsForSeveralGoalsAndRobots_whenQueriedByRobotAndGoal_thenOnlyMatchesReturn() {
        patterns.save(pattern("bittle-1", "look_upward", List.of("look_up"), 1, 1));
        patterns.save(pattern("bittle-1", "look_upward", List.of("sit", "look_up"), 1, 0));
        patterns.save(pattern("bittle-1", "sit_down", List.of("sit"), 1, 1));
        patterns.save(pattern("bittle-2", "look_upward", List.of("look_up"), 1, 1));

        var found = patterns.findByRobotIdAndGoal("bittle-1", "look_upward");

        assertThat(found).hasSize(2)
                .allSatisfy(p -> {
                    assertThat(p.robotId()).isEqualTo("bittle-1");
                    assertThat(p.goal()).isEqualTo("look_upward");
                });
    }

    @Test
    void givenPatterns_whenQueriedBySuccessRate_thenHighestRateComesFirstAndTiesPreferMoreAttempts() {
        patterns.save(pattern("bittle-1", "look_upward", List.of("a"), 4, 1));   // 0.25
        patterns.save(pattern("bittle-1", "look_upward", List.of("b"), 2, 2));   // 1.0, 2 attempts
        patterns.save(pattern("bittle-1", "look_upward", List.of("c"), 10, 10)); // 1.0, 10 attempts
        patterns.save(pattern("bittle-1", "look_upward", List.of("d"), 2, 1));   // 0.5

        var ranked = patterns.findByRobotIdAndGoalOrderBySuccessRateDesc("bittle-1", "look_upward");

        assertThat(ranked).extracting(p -> p.toolCombination().get(0))
                .containsExactly("c", "b", "d", "a");
    }

    @Test
    void givenPatternsWithDifferentStatuses_whenQueriedByStatus_thenOnlyThatStatusReturns() {
        var active = patterns.save(pattern("bittle-1", "look_upward", List.of("a"), 1, 1));
        var deprecated = patterns.save(pattern("bittle-1", "look_upward", List.of("b"), 1, 0)
                .withStatus(PatternStatus.DEPRECATED, T0));
        patterns.save(pattern("bittle-2", "look_upward", List.of("a"), 1, 1));

        assertThat(patterns.findByRobotIdAndStatus("bittle-1", PatternStatus.ACTIVE))
                .extracting(LearnedPattern::id).containsExactly(active.id());
        assertThat(patterns.findByRobotIdAndStatus("bittle-1", PatternStatus.DEPRECATED))
                .extracting(LearnedPattern::id).containsExactly(deprecated.id());
        assertThat(patterns.findByRobotIdAndStatus("bittle-1", PatternStatus.INACTIVE)).isEmpty();
    }

    @Test
    void givenCombination_whenLookedUpByExactOrderedTools_thenOrderMatters() {
        var saved = patterns.save(pattern("bittle-1", "look_upward", List.of("sit", "look_up"), 1, 1));

        assertThat(patterns.findByRobotIdAndGoalAndToolCombination("bittle-1", "look_upward",
                List.of("sit", "look_up"))).map(LearnedPattern::id).contains(saved.id());
        assertThat(patterns.findByRobotIdAndGoalAndToolCombination("bittle-1", "look_upward",
                List.of("look_up", "sit"))).isEmpty();
        assertThat(patterns.findByRobotIdAndGoalAndToolCombination("bittle-1", "sit_down",
                List.of("sit", "look_up"))).isEmpty();
    }

    @Test
    void givenExistingCombination_whenADuplicateKeyRowIsInserted_thenTheUniqueConstraintRejectsIt() {
        patterns.save(pattern("bittle-1", "look_upward", List.of("look_up"), 1, 1));

        assertThatThrownBy(() -> {
            patterns.save(pattern("bittle-1", "look_upward", List.of("look_up"), 1, 0));
            jpa.flush();
        }).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void givenCombination_whenSerialized_thenKeyIsACompactJsonArray() {
        assertThat(patterns.write(List.of("sit", "look_up"))).isEqualTo("[\"sit\",\"look_up\"]");
    }
}

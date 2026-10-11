package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.LearnedPatternRepositoryPort;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.PatternStatus;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class LearnedPatternQueriesTest {

    private static final Instant T0 = Instant.parse("2026-10-11T21:45:00Z");

    private final LearnedPatternRepositoryPort repository = mock(LearnedPatternRepositoryPort.class);
    private final StepClock clock = new StepClock(T0);
    private final LearnedPatternQueries queries = new LearnedPatternQueries(repository,
            new Fleet(List.of(new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika"))),
            clock, LearnedPatternQueries.DEFAULT_TTL);

    @Test
    void givenPatterns_whenQueried_thenOnlyActiveOnesInRepositoryOrder() {
        var best = pattern("a", 10, 9);
        var retired = pattern("b", 0, 0).withStatus(PatternStatus.INACTIVE, T0);
        var worse = pattern("c", 10, 2);
        when(repository.findByRobotIdAndGoalOrderBySuccessRateDesc("bittle-1", "bark"))
                .thenReturn(List.of(best, retired, worse));

        assertThat(queries.activePatterns("bittle-1", "bark")).containsExactly(best, worse);
    }

    @Test
    void givenRepeatedQuery_whenWithinFiveSeconds_thenCachedAndRefreshedAfterwards() {
        when(repository.findByRobotIdAndGoalOrderBySuccessRateDesc("bittle-1", "bark"))
                .thenReturn(List.of(pattern("a", 1, 1)));

        queries.activePatterns("bittle-1", "bark");
        clock.advance(Duration.ofSeconds(4));
        queries.activePatterns("bittle-1", "bark");
        verify(repository, times(1)).findByRobotIdAndGoalOrderBySuccessRateDesc("bittle-1", "bark");

        clock.advance(Duration.ofSeconds(2));
        queries.activePatterns("bittle-1", "bark");
        verify(repository, times(2)).findByRobotIdAndGoalOrderBySuccessRateDesc("bittle-1", "bark");
    }

    @Test
    void givenDifferentGoals_whenQueried_thenCachedSeparately() {
        when(repository.findByRobotIdAndGoalOrderBySuccessRateDesc("bittle-1", "bark"))
                .thenReturn(List.of(pattern("a", 1, 1)));
        when(repository.findByRobotIdAndGoalOrderBySuccessRateDesc("bittle-1", "tilt_head"))
                .thenReturn(List.of());

        assertThat(queries.activePatterns("bittle-1", "bark")).hasSize(1);
        assertThat(queries.activePatterns("bittle-1", "tilt_head")).isEmpty();
    }

    @Test
    void givenUnknownRobotOrBlankGoal_whenQueried_thenRejected() {
        assertThatThrownBy(() -> queries.activePatterns("ghost", "bark"))
                .isInstanceOf(RobotNotFoundException.class);
        assertThatThrownBy(() -> queries.activePatterns("bittle-1", " "))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> queries.activePatterns("bittle-1", null))
                .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(repository);
    }

    private static LearnedPattern pattern(String tool, int attempts, int successes) {
        return LearnedPattern.discovered("bittle-1", "bark", List.of(tool), T0)
                .withStats(attempts, successes, T0, T0);
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

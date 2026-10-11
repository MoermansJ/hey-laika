package com.bittle.orchestrator.adapter.out.metrics;

import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class MicrometerAgentMetricsAdapterTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final MicrometerAgentMetricsAdapter metrics = new MicrometerAgentMetricsAdapter(registry);

    @Test
    void givenOutcomes_whenRecorded_thenCountedPerGoalAndResult() {
        metrics.recordOutcome("bark", true);
        metrics.recordOutcome("bark", true);
        metrics.recordOutcome("bark", false);
        metrics.recordOutcome(null, null);

        assertThat(registry.counter(MicrometerAgentMetricsAdapter.OUTCOMES, "goal", "bark",
                "result", "success").count()).isEqualTo(2.0);
        assertThat(registry.counter(MicrometerAgentMetricsAdapter.OUTCOMES, "goal", "bark",
                "result", "failure").count()).isEqualTo(1.0);
        assertThat(registry.counter(MicrometerAgentMetricsAdapter.OUTCOMES, "goal", "none",
                "result", "undetermined").count()).isEqualTo(1.0);
    }

    @Test
    void givenRollups_whenRecorded_thenTimerAndPatternCountAreKept() {
        metrics.recordRollup("bark", 3, TimeUnit.MILLISECONDS.toNanos(2));
        metrics.recordRollupFailure("bark");

        var timer = registry.find(MicrometerAgentMetricsAdapter.ROLLUP).tag("goal", "bark").timer();
        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(2.0);
        assertThat(registry.find(MicrometerAgentMetricsAdapter.ROLLUP_PATTERNS).tag("goal", "bark")
                .summary().max()).isEqualTo(3.0);
        assertThat(registry.counter(MicrometerAgentMetricsAdapter.ROLLUP_FAILURES, "goal", "bark")
                .count()).isEqualTo(1.0);
    }
}

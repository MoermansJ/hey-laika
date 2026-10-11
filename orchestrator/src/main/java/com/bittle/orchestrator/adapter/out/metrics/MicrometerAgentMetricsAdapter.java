package com.bittle.orchestrator.adapter.out.metrics;

import com.bittle.orchestrator.application.port.out.AgentMetricsPort;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

/**
 * Micrometer meters for agent runs (AGENT-12), visible under /actuator/metrics:
 * <ul>
 *   <li>{@code bittle.agent.submissions} — counter, tags tool and result
 *       (accepted | rejected | mode_rejected)</li>
 *   <li>{@code bittle.agent.outcomes} — counter, tags goal and result
 *       (success | failure | undetermined)</li>
 *   <li>{@code bittle.agent.pattern.rollup} — timer per goal</li>
 *   <li>{@code bittle.agent.pattern.rollup.patterns} — distribution of active patterns per rollup</li>
 *   <li>{@code bittle.agent.pattern.rollup.failures} — counter per goal</li>
 * </ul>
 */
@Component
public class MicrometerAgentMetricsAdapter implements AgentMetricsPort {

    static final String SUBMISSIONS = "bittle.agent.submissions";
    static final String OUTCOMES = "bittle.agent.outcomes";
    static final String ROLLUP = "bittle.agent.pattern.rollup";
    static final String ROLLUP_PATTERNS = "bittle.agent.pattern.rollup.patterns";
    static final String ROLLUP_FAILURES = "bittle.agent.pattern.rollup.failures";

    private final MeterRegistry meterRegistry;

    public MicrometerAgentMetricsAdapter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void recordSubmission(String tool, String result) {
        meterRegistry.counter(SUBMISSIONS, "tool", tag(tool), "result", tag(result)).increment();
    }

    @Override
    public void recordOutcome(String goal, Boolean success) {
        String result = success == null ? "undetermined" : (success ? "success" : "failure");
        meterRegistry.counter(OUTCOMES, "goal", tag(goal), "result", result).increment();
    }

    @Override
    public void recordRollup(String goal, int activePatterns, long durationNanos) {
        Timer.builder(ROLLUP).tag("goal", tag(goal)).register(meterRegistry)
                .record(durationNanos, TimeUnit.NANOSECONDS);
        meterRegistry.summary(ROLLUP_PATTERNS, "goal", tag(goal)).record(activePatterns);
    }

    @Override
    public void recordRollupFailure(String goal) {
        meterRegistry.counter(ROLLUP_FAILURES, "goal", tag(goal)).increment();
    }

    private static String tag(String goal) {
        return goal == null || goal.isBlank() ? "none" : goal;
    }
}

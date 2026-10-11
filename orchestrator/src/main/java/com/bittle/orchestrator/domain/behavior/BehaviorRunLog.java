package com.bittle.orchestrator.domain.behavior;

import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * One behavior execution as seen by the orchestrator
 * (AGENT_TOOL_COMPOSITION_DESIGN.md §2.1). Agent runs carry a declared
 * {@code goal} and, once evaluated, an {@link OutcomeEvaluation}; both stay
 * null for manual, lifecycle and safety runs.
 */
public record BehaviorRunLog(UUID id, String robotId, Instant timestamp, Instant completedAt,
                             String behaviorName, String source, Integer priority,
                             Map<String, Object> cause, Long executionTimeMs, String preemptedBy,
                             String goal, OutcomeEvaluation outcome,
                             Map<String, Object> sensorDelta,
                             Instant createdAt, Instant updatedAt) {

    public BehaviorRunLog {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(robotId, "robotId");
        Objects.requireNonNull(timestamp, "timestamp");
        cause = copy(cause);
        sensorDelta = copy(sensorDelta);
    }

    /** True once an outcome evaluation has been attached. */
    public boolean hasOutcome() {
        return outcome != null;
    }

    /** Copy of this run with the given outcome attached and {@code updatedAt} set. */
    public BehaviorRunLog withOutcome(OutcomeEvaluation newOutcome, Instant now) {
        return new BehaviorRunLog(id, robotId, timestamp, completedAt, behaviorName, source,
                priority, cause, executionTimeMs, preemptedBy, goal, newOutcome, sensorDelta,
                createdAt, now);
    }

    private static Map<String, Object> copy(Map<String, Object> map) {
        // LinkedHashMap rather than Map.copyOf: adapter payloads may hold null values.
        return map == null ? null : Collections.unmodifiableMap(new LinkedHashMap<>(map));
    }
}

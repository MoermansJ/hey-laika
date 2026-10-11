package com.bittle.orchestrator.domain.behavior;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * A named behavior handed to the adapter's arbiter
 * (AGENT_TOOL_COMPOSITION_DESIGN.md §2.3). Agent submissions always run at
 * {@link #AGENT_PRIORITY} with {@code source = "agent"} and a cause of
 * {@code {"type": "agent", "decisionId": ...}}.
 *
 * @param behaviorName named behavior from the adapter's behavior store
 * @param source       provenance: "agent", "manual", ...
 * @param priority     arbiter priority (lower wins); null lets the adapter pick its default
 * @param goal         goal the agent declares for this run; null for non-agent runs
 * @param cause        provenance details, e.g. {"type": "agent", "decisionId": "&lt;uuid&gt;"}
 * @param parameters   optional parameters for a parametric behavior (rare)
 */
public record ArbiterSubmissionRequest(String behaviorName, String source, Integer priority,
                                       String goal, Map<String, Object> cause,
                                       Map<String, Object> parameters) {

    public static final int AGENT_PRIORITY = 3;
    public static final String SOURCE_AGENT = "agent";

    public ArbiterSubmissionRequest {
        Objects.requireNonNull(behaviorName, "behaviorName");
        if (behaviorName.isBlank()) {
            throw new IllegalArgumentException("behaviorName must not be blank");
        }
        Objects.requireNonNull(source, "source");
        cause = copy(cause);
        parameters = copy(parameters);
    }

    /** An agent tool call: priority 3, source "agent", cause carrying the decision id. */
    public static ArbiterSubmissionRequest forAgent(String behaviorName, String goal,
                                                    String decisionId) {
        Map<String, Object> cause = new LinkedHashMap<>();
        cause.put("type", SOURCE_AGENT);
        cause.put("decisionId", decisionId);
        return new ArbiterSubmissionRequest(behaviorName, SOURCE_AGENT, AGENT_PRIORITY, goal,
                cause, null);
    }

    /** The decision id from {@link #cause()}, or null when there is none. */
    public String decisionId() {
        Object id = cause == null ? null : cause.get("decisionId");
        return id == null ? null : id.toString();
    }

    private static Map<String, Object> copy(Map<String, Object> map) {
        return map == null ? null : Collections.unmodifiableMap(new LinkedHashMap<>(map));
    }
}

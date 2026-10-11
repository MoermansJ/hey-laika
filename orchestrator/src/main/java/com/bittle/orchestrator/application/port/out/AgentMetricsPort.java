package com.bittle.orchestrator.application.port.out;

/** Metrics for the agent tool-call lifecycle (AGENT-12). Implementations must not throw. */
public interface AgentMetricsPort {

    /**
     * An agent tool call was answered: {@code result} is accepted, rejected (by the
     * arbiter or a connection error) or mode_rejected (not allowed in the mode).
     */
    void recordSubmission(String tool, String result);

    /** An agent run was closed with an outcome; {@code success} null = undetermined. */
    void recordOutcome(String goal, Boolean success);

    /** A pattern rollup for the goal finished with this many active patterns. */
    void recordRollup(String goal, int activePatterns, long durationNanos);

    /** A pattern rollup for the goal failed. */
    void recordRollupFailure(String goal);
}

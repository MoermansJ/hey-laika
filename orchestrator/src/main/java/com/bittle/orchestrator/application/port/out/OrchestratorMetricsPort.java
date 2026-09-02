package com.bittle.orchestrator.application.port.out;

/** The orchestrator's own runtime numbers (HTTP traffic, adapter failures). */
public interface OrchestratorMetricsPort {

    HttpStats httpStats();

    long adapterUnavailableCount();

    /** Counts a proxied call that found the adapter down. */
    void recordAdapterUnavailable();

    record HttpStats(long requestCount, double totalMs, double maxMs) {
    }
}

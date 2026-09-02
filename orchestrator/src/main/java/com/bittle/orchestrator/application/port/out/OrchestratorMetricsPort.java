package com.bittle.orchestrator.application.port.out;

public interface OrchestratorMetricsPort {

    HttpStats httpStats();

    long adapterUnavailableCount();

    void recordAdapterUnavailable();

    record HttpStats(long requestCount, double totalMs, double maxMs) {
    }
}

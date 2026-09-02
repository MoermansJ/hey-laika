package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class OrchestratorMetricsSnapshot {

    public static final String ORCHESTRATOR_ID = "orchestrator";

    private final OrchestratorMetricsPort metrics;
    private final Instant startedAt = Instant.now();

    public OrchestratorMetricsSnapshot(OrchestratorMetricsPort metrics) {
        this.metrics = metrics;
    }

    public Map<String, Object> snapshot() {
        var http = metrics.httpStats();
        long count = http.requestCount();

        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put("uptimeS", Duration.between(startedAt, Instant.now()).toSeconds());
        snapshot.put("httpRequests", count);
        snapshot.put("httpAvgMs", count > 0 ? Math.round(http.totalMs() / count * 10) / 10.0 : 0.0);
        snapshot.put("httpMaxMs", Math.round(http.maxMs() * 10) / 10.0);
        snapshot.put("adapterUnavailable", metrics.adapterUnavailableCount());
        return snapshot;
    }
}

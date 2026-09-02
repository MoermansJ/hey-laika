package com.bittle.orchestrator.application.port.in;

import java.util.List;
import java.util.Map;

/** Fleet-wide usage metrics: live merge plus hourly history. */
public interface MetricsUseCase {

    /** Live fleet-wide metrics: orchestrator + every adapter's snapshot. */
    Map<String, Object> merged();

    /** Hourly rollups for one robot (or "orchestrator"), newest first. */
    List<Map<String, Object>> history(String robotId, int limit);

    /** Persists the current hour's snapshot for the orchestrator and every robot. */
    void rollupHour();
}

package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.port.in.MetricsUseCase;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MetricsController {

    private final MetricsUseCase metrics;

    public MetricsController(MetricsUseCase metrics) {
        this.metrics = metrics;
    }

    /** Live fleet-wide metrics: orchestrator + every adapter's snapshot. */
    @GetMapping("/api/metrics")
    public Map<String, Object> metrics() {
        return metrics.merged();
    }

    /** Hourly rollups for one robot (or "orchestrator"), newest first. */
    @GetMapping("/api/metrics/history")
    public List<Map<String, Object>> history(
            @RequestParam String robotId,
            @RequestParam(defaultValue = "168") int limit) {
        return metrics.history(robotId, Math.min(Math.max(limit, 1), 2000));
    }
}

package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetMergedMetricsUseCase;
import com.bittle.orchestrator.application.usecase.GetMetricsHistoryUseCase;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MetricsController {

    private static final int MIN_HISTORY_LIMIT = 1;
    private static final int MAX_HISTORY_LIMIT = 2000;

    private final GetMergedMetricsUseCase getMergedMetrics;
    private final GetMetricsHistoryUseCase getHistory;

    public MetricsController(GetMergedMetricsUseCase getMergedMetrics,
                             GetMetricsHistoryUseCase getHistory) {
        this.getMergedMetrics = getMergedMetrics;
        this.getHistory = getHistory;
    }

    @GetMapping("/api/metrics")
    public Map<String, Object> metrics() {
        return getMergedMetrics.execute();
    }

    @GetMapping("/api/metrics/history")
    public List<Map<String, Object>> history(
            @RequestParam String robotId,
            @RequestParam(defaultValue = "168") int limit) {
        return getHistory.execute(robotId,
                Math.min(Math.max(limit, MIN_HISTORY_LIMIT), MAX_HISTORY_LIMIT));
    }
}

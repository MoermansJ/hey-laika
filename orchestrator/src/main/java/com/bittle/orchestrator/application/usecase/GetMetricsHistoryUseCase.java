package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort;
import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort.MetricsRollupRecord;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class GetMetricsHistoryUseCase {

    private final MetricsRollupRepositoryPort rollups;

    public GetMetricsHistoryUseCase(MetricsRollupRepositoryPort rollups) {
        this.rollups = rollups;
    }

    public List<Map<String, Object>> execute(String robotId, int limit) {
        return rollups.findLatest(robotId, limit).stream()
                .map(GetMetricsHistoryUseCase::row)
                .toList();
    }

    private static Map<String, Object> row(MetricsRollupRecord rollup) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("robotId", rollup.robotId());
        row.put("hourStart", rollup.hourStart().toString());
        row.put("snapshot", rollup.snapshot());
        return row;
    }
}

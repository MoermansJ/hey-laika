package com.bittle.orchestrator.application.port.out;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public interface MetricsRollupRepositoryPort {

    void save(String robotId, Instant hourStart, Map<String, Object> snapshot);

    List<MetricsRollupRecord> findLatest(String robotId, int limit);

    record MetricsRollupRecord(String robotId, Instant hourStart, Object snapshot) {
    }
}

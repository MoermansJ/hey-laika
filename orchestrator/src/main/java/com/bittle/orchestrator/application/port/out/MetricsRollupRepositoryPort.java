package com.bittle.orchestrator.application.port.out;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Hourly usage-metrics snapshots per robot (plus "orchestrator"), kept permanently. */
public interface MetricsRollupRepositoryPort {

    void save(String robotId, Instant hourStart, Map<String, Object> snapshot);

    /** Newest first, at most {@code limit} entries. */
    List<MetricsRollupRecord> findLatest(String robotId, int limit);

    /** {@code snapshot} is the parsed map, or the raw stored text when it cannot be parsed. */
    record MetricsRollupRecord(String robotId, Instant hourStart, Object snapshot) {
    }
}

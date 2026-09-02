package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Component;

/** Stores rollup snapshots as JSON text; parses them back on read. */
@Component
public class MetricsRollupRepositoryAdapter implements MetricsRollupRepositoryPort {

    private static final Logger log = LoggerFactory.getLogger(MetricsRollupRepositoryAdapter.class);

    private final MetricsRollupJpaRepository repository;
    private final ObjectMapper objectMapper;

    public MetricsRollupRepositoryAdapter(MetricsRollupJpaRepository repository,
                                          ObjectMapper objectMapper) {
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    @Override
    public void save(String robotId, Instant hourStart, Map<String, Object> snapshot) {
        try {
            var rollup = new MetricsRollupEntity();
            rollup.setRobotId(robotId);
            rollup.setHourStart(hourStart);
            rollup.setSnapshotJson(objectMapper.writeValueAsString(snapshot));
            repository.save(rollup);
        } catch (JsonProcessingException e) {
            log.error("Metrics rollup for {} not serializable", robotId, e);
        }
    }

    @Override
    public List<MetricsRollupRecord> findLatest(String robotId, int limit) {
        return repository.findByRobotIdOrderByHourStartDesc(robotId, PageRequest.of(0, limit))
                .stream()
                .map(entity -> new MetricsRollupRecord(entity.getRobotId(), entity.getHourStart(),
                        parse(entity.getSnapshotJson())))
                .toList();
    }

    /** Falls back to the raw text when a stored snapshot cannot be parsed. */
    private Object parse(String json) {
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (JsonProcessingException e) {
            return json;
        }
    }
}

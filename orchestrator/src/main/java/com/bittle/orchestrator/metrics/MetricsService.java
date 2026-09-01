package com.bittle.orchestrator.metrics;

import com.bittle.orchestrator.fleet.FleetManager;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/**
 * Fleet-wide metrics: merges the adapters' /metrics snapshots with the
 * orchestrator's own Micrometer numbers, and rolls usage totals up into
 * Postgres hourly (kept permanently — accounting survives restarts; the
 * fine-grained windows live only in the adapters' memory).
 */
@Service
public class MetricsService {

    private static final Logger log = LoggerFactory.getLogger(MetricsService.class);

    /** Counter name for proxied calls that found the adapter down. */
    public static final String ADAPTER_UNAVAILABLE_COUNTER = "bittle.adapter.unavailable";

    private final FleetManager fleetManager;
    private final MeterRegistry meterRegistry;
    private final MetricsRollupRepository repository;
    private final ObjectMapper objectMapper;
    private final Instant startedAt = Instant.now();
    private final double claudeInPerMtok;
    private final double claudeOutPerMtok;

    public MetricsService(FleetManager fleetManager, MeterRegistry meterRegistry,
                          MetricsRollupRepository repository, ObjectMapper objectMapper,
                          @Value("${metrics.claude-input-usd-per-mtok:15.0}") double claudeInPerMtok,
                          @Value("${metrics.claude-output-usd-per-mtok:75.0}") double claudeOutPerMtok) {
        this.fleetManager = fleetManager;
        this.meterRegistry = meterRegistry;
        this.repository = repository;
        this.objectMapper = objectMapper;
        this.claudeInPerMtok = claudeInPerMtok;
        this.claudeOutPerMtok = claudeOutPerMtok;
    }

    public Map<String, Object> merged() {
        Map<String, Object> merged = new LinkedHashMap<>();
        merged.put("orchestrator", orchestratorMetrics());
        Map<String, Object> robots = new LinkedHashMap<>();
        fleetManager.all().forEach(agent -> {
            try {
                robots.put(agent.id(), priced(agent.metricsSnapshot()));
            } catch (RuntimeException e) {
                robots.put(agent.id(), Map.of("error", "adapter_unavailable",
                        "message", String.valueOf(e.getMessage())));
            }
        });
        merged.put("robots", robots);
        return merged;
    }

    /** Adapters measure exact token counts; only the orchestrator prices
     *  them (metrics brief D.2). Adds estCostUsd when Claude tokens exist. */
    @SuppressWarnings("unchecked")
    private Map<String, Object> priced(Map<String, Object> snapshot) {
        Object countersObj = snapshot.get("counters");
        if (countersObj instanceof Map<?, ?> counters) {
            double in = asDouble(counters.get("ai.claude.tokensIn"));
            double out = asDouble(counters.get("ai.claude.tokensOut"));
            if (in > 0 || out > 0) {
                double cost = in / 1_000_000.0 * claudeInPerMtok
                        + out / 1_000_000.0 * claudeOutPerMtok;
                snapshot.put("estCostUsd", Math.round(cost * 10000) / 10000.0);
            }
        }
        return snapshot;
    }

    private static double asDouble(Object value) {
        return value instanceof Number n ? n.doubleValue() : 0.0;
    }

    public Map<String, Object> orchestratorMetrics() {
        var timers = meterRegistry.find("http.server.requests").timers();
        long count = timers.stream().mapToLong(Timer::count).sum();
        double totalMs = timers.stream()
                .mapToDouble(t -> t.totalTime(TimeUnit.MILLISECONDS)).sum();
        double maxMs = timers.stream()
                .mapToDouble(t -> t.max(TimeUnit.MILLISECONDS)).max().orElse(0.0);

        Map<String, Object> metrics = new LinkedHashMap<>();
        metrics.put("uptimeS", Duration.between(startedAt, Instant.now()).toSeconds());
        metrics.put("httpRequests", count);
        metrics.put("httpAvgMs", count > 0 ? Math.round(totalMs / count * 10) / 10.0 : 0.0);
        metrics.put("httpMaxMs", Math.round(maxMs * 10) / 10.0);
        metrics.put("adapterUnavailable",
                (long) meterRegistry.counter(ADAPTER_UNAVAILABLE_COUNTER).count());
        return metrics;
    }

    public List<Map<String, Object>> history(String robotId, int limit) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (MetricsRollup rollup : repository.findByRobotIdOrderByHourStartDesc(
                robotId, PageRequest.of(0, limit))) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("robotId", rollup.getRobotId());
            row.put("hourStart", rollup.getHourStart().toString());
            row.put("snapshot", parse(rollup.getSnapshotJson()));
            out.add(row);
        }
        return out;
    }

    @Scheduled(cron = "0 0 * * * *")
    public void rollup() {
        Instant hourStart = Instant.now().truncatedTo(ChronoUnit.HOURS);
        save("orchestrator", hourStart, orchestratorMetrics());
        fleetManager.all().forEach(agent -> {
            try {
                save(agent.id(), hourStart, agent.metricsSnapshot());
            } catch (RuntimeException e) {
                log.warn("Metrics rollup skipped for {} (adapter unreachable): {}",
                        agent.id(), e.getMessage());
            }
        });
    }

    private void save(String robotId, Instant hourStart, Map<String, Object> snapshot) {
        try {
            MetricsRollup rollup = new MetricsRollup();
            rollup.setRobotId(robotId);
            rollup.setHourStart(hourStart);
            rollup.setSnapshotJson(objectMapper.writeValueAsString(snapshot));
            repository.save(rollup);
        } catch (JsonProcessingException e) {
            log.error("Metrics rollup for {} not serializable", robotId, e);
        }
    }

    private Object parse(String json) {
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (JsonProcessingException e) {
            return json;
        }
    }
}

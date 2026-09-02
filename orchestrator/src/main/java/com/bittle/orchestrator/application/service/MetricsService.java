package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.MetricsSettings;
import com.bittle.orchestrator.application.port.in.MetricsUseCase;
import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort;
import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort.MetricsRollupRecord;
import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Fleet-wide metrics: merges the adapters' metrics snapshots with the
 * orchestrator's own numbers, and rolls usage totals up hourly (kept
 * permanently — accounting survives restarts; the fine-grained windows live
 * only in the adapters' memory).
 */
public class MetricsService implements MetricsUseCase {

    private static final Logger log = LoggerFactory.getLogger(MetricsService.class);
    private static final String ORCHESTRATOR_ID = "orchestrator";

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;
    private final OrchestratorMetricsPort orchestratorMetrics;
    private final MetricsRollupRepositoryPort rollups;
    private final MetricsSettings settings;
    private final Instant startedAt = Instant.now();

    public MetricsService(FleetRegistry registry, RobotAdapterPort adapter,
                          OrchestratorMetricsPort orchestratorMetrics,
                          MetricsRollupRepositoryPort rollups, MetricsSettings settings) {
        this.registry = registry;
        this.adapter = adapter;
        this.orchestratorMetrics = orchestratorMetrics;
        this.rollups = rollups;
        this.settings = settings;
    }

    @Override
    public Map<String, Object> merged() {
        Map<String, Object> merged = new LinkedHashMap<>();
        merged.put(ORCHESTRATOR_ID, orchestratorMetrics());
        Map<String, Object> robots = new LinkedHashMap<>();
        registry.all().forEach(robot -> {
            try {
                robots.put(robot.id(), priced(adapter.metrics(robot)));
            } catch (RuntimeException e) {
                robots.put(robot.id(), Map.of("error", "adapter_unavailable",
                        "message", String.valueOf(e.getMessage())));
            }
        });
        merged.put("robots", robots);
        return merged;
    }

    /** Adapters measure exact token counts; only the orchestrator prices
     *  them (metrics brief D.2). Adds estCostUsd when Claude tokens exist. */
    private Map<String, Object> priced(Map<String, Object> snapshot) {
        if (snapshot.get("counters") instanceof Map<?, ?> counters) {
            double in = asDouble(counters.get("ai.claude.tokensIn"));
            double out = asDouble(counters.get("ai.claude.tokensOut"));
            if (in > 0 || out > 0) {
                double cost = in / 1_000_000.0 * settings.claudeInputUsdPerMtok()
                        + out / 1_000_000.0 * settings.claudeOutputUsdPerMtok();
                snapshot.put("estCostUsd", Math.round(cost * 10000) / 10000.0);
            }
        }
        return snapshot;
    }

    private static double asDouble(Object value) {
        return value instanceof Number n ? n.doubleValue() : 0.0;
    }

    private Map<String, Object> orchestratorMetrics() {
        var http = orchestratorMetrics.httpStats();
        long count = http.requestCount();

        Map<String, Object> metrics = new LinkedHashMap<>();
        metrics.put("uptimeS", Duration.between(startedAt, Instant.now()).toSeconds());
        metrics.put("httpRequests", count);
        metrics.put("httpAvgMs", count > 0 ? Math.round(http.totalMs() / count * 10) / 10.0 : 0.0);
        metrics.put("httpMaxMs", Math.round(http.maxMs() * 10) / 10.0);
        metrics.put("adapterUnavailable", orchestratorMetrics.adapterUnavailableCount());
        return metrics;
    }

    @Override
    public List<Map<String, Object>> history(String robotId, int limit) {
        return rollups.findLatest(robotId, limit).stream()
                .map(MetricsService::row)
                .toList();
    }

    private static Map<String, Object> row(MetricsRollupRecord rollup) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("robotId", rollup.robotId());
        row.put("hourStart", rollup.hourStart().toString());
        row.put("snapshot", rollup.snapshot());
        return row;
    }

    @Override
    public void rollupHour() {
        var hourStart = Instant.now().truncatedTo(ChronoUnit.HOURS);
        rollups.save(ORCHESTRATOR_ID, hourStart, orchestratorMetrics());
        registry.all().forEach(robot -> rollup(robot, hourStart));
    }

    private void rollup(Robot robot, Instant hourStart) {
        try {
            rollups.save(robot.id(), hourStart, adapter.metrics(robot));
        } catch (RuntimeException e) {
            log.warn("Metrics rollup skipped for {} (adapter unreachable): {}",
                    robot.id(), e.getMessage());
        }
    }
}

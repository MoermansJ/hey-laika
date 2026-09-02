package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.MetricsSettings;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.application.service.OrchestratorMetricsSnapshot;
import java.util.LinkedHashMap;
import java.util.Map;

public class GetMergedMetricsUseCase {

    private static final double TOKENS_PER_MILLION = 1_000_000.0;

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;
    private final OrchestratorMetricsSnapshot orchestrator;
    private final MetricsSettings settings;

    public GetMergedMetricsUseCase(FleetRegistry registry, RobotAdapterPort adapter,
                                   OrchestratorMetricsSnapshot orchestrator,
                                   MetricsSettings settings) {
        this.registry = registry;
        this.adapter = adapter;
        this.orchestrator = orchestrator;
        this.settings = settings;
    }

    public Map<String, Object> execute() {
        Map<String, Object> merged = new LinkedHashMap<>();
        merged.put(OrchestratorMetricsSnapshot.ORCHESTRATOR_ID, orchestrator.snapshot());
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

    private Map<String, Object> priced(Map<String, Object> snapshot) {
        if (snapshot.get("counters") instanceof Map<?, ?> counters) {
            double in = asDouble(counters.get("ai.claude.tokensIn"));
            double out = asDouble(counters.get("ai.claude.tokensOut"));
            if (in > 0 || out > 0) {
                double cost = in / TOKENS_PER_MILLION * settings.claudeInputUsdPerMtok()
                        + out / TOKENS_PER_MILLION * settings.claudeOutputUsdPerMtok();
                snapshot.put("estCostUsd", Math.round(cost * 10000) / 10000.0);
            }
        }
        return snapshot;
    }

    private static double asDouble(Object value) {
        return value instanceof Number n ? n.doubleValue() : 0.0;
    }
}

package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.MetricsSettings;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.application.service.OrchestratorMetricsSnapshot;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.DecisionModel;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class GetMergedMetricsUseCase {

    private static final double TOKENS_PER_MILLION = 1_000_000.0;
    private static final long MODEL_CACHE_MS = 5 * 60_000;

    private final Fleet fleet;
    private final RobotAdapterPort adapter;
    private final OrchestratorMetricsSnapshot orchestrator;
    private final MetricsSettings settings;
    private final Map<String, DecisionModel> models = new ConcurrentHashMap<>();
    private final Map<String, Long> modelsAt = new ConcurrentHashMap<>();

    public GetMergedMetricsUseCase(Fleet fleet, RobotAdapterPort adapter,
                                   OrchestratorMetricsSnapshot orchestrator,
                                   MetricsSettings settings) {
        this.fleet = fleet;
        this.adapter = adapter;
        this.orchestrator = orchestrator;
        this.settings = settings;
    }

    public Map<String, Object> execute() {
        Map<String, Object> merged = new LinkedHashMap<>();
        merged.put(OrchestratorMetricsSnapshot.ORCHESTRATOR_ID, orchestrator.snapshot());
        Map<String, Object> robots = new LinkedHashMap<>();
        fleet.all().forEach(robot -> {
            try {
                robots.put(robot.id(), priced(robot, adapter.metrics(robot)));
            } catch (RuntimeException e) {
                robots.put(robot.id(), Map.of("error", "adapter_unavailable",
                        "message", String.valueOf(e.getMessage())));
            }
        });
        merged.put("robots", robots);
        return merged;
    }

    private Map<String, Object> priced(Robot robot, Map<String, Object> snapshot) {
        var configured = configuredModel(robot);
        snapshot.put("decisionEngine", configured.engine());
        snapshot.put("decisionModel", configured.model());
        if (snapshot.get("counters") instanceof Map<?, ?> counters) {
            double in = asDouble(counters.get("ai.claude.tokensIn"));
            double out = asDouble(counters.get("ai.claude.tokensOut"));
            if (in > 0 || out > 0) {
                var pricedModel = configured.isClaude() ? configured.model() : settings.defaultModel();
                var price = settings.priceFor(pricedModel);
                double cost = in / TOKENS_PER_MILLION * price.inputUsdPerMtok()
                        + out / TOKENS_PER_MILLION * price.outputUsdPerMtok();
                snapshot.put("estCostUsd", Math.round(cost * 10000) / 10000.0);
                snapshot.put("pricedModel", pricedModel);
            }
        }
        return snapshot;
    }

    private DecisionModel configuredModel(Robot robot) {
        long now = System.currentTimeMillis();
        var at = modelsAt.get(robot.id());
        if (at != null && now - at < MODEL_CACHE_MS) {
            return models.getOrDefault(robot.id(), DecisionModel.UNKNOWN);
        }
        try {
            var schema = adapter.capabilities(robot);
            var metadata = schema.get("metadata") instanceof Map<?, ?> m ? m : Map.of();
            models.put(robot.id(), new DecisionModel(asString(metadata.get("decisionEngine")),
                    asString(metadata.get("decisionModel"))));
        } catch (RuntimeException e) {
            models.putIfAbsent(robot.id(), DecisionModel.UNKNOWN);
        }
        modelsAt.put(robot.id(), now);
        return models.get(robot.id());
    }

    private static String asString(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static double asDouble(Object value) {
        return value instanceof Number n ? n.doubleValue() : 0.0;
    }
}

package com.bittle.orchestrator.infrastructure.config;

import com.bittle.orchestrator.application.MetricsSettings;
import com.bittle.orchestrator.application.MetricsSettings.ModelPrice;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "metrics")
public record MetricsProperties(
        @DefaultValue("claude-opus-5") String defaultModel,
        Map<String, Price> prices) {

    public record Price(double inputUsdPerMtok, double outputUsdPerMtok) {
    }

    public MetricsSettings toSettings() {
        Map<String, ModelPrice> table = new LinkedHashMap<>();
        table.put("claude-opus-5", new ModelPrice(5.0, 25.0));
        table.put("claude-opus-4-8", new ModelPrice(5.0, 25.0));
        table.put("claude-sonnet-5", new ModelPrice(2.0, 10.0));
        table.put("claude-sonnet-4-6", new ModelPrice(3.0, 15.0));
        table.put("claude-haiku-4-5", new ModelPrice(1.0, 5.0));
        if (prices != null) {
            prices.forEach((model, price) ->
                    table.put(model, new ModelPrice(price.inputUsdPerMtok(), price.outputUsdPerMtok())));
        }
        return new MetricsSettings(Map.copyOf(table), defaultModel);
    }
}

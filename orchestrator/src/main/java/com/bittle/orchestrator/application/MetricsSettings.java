package com.bittle.orchestrator.application;

import java.util.Map;

public record MetricsSettings(Map<String, ModelPrice> prices, String defaultModel) {

    public record ModelPrice(double inputUsdPerMtok, double outputUsdPerMtok) {
    }

    public ModelPrice priceFor(String model) {
        if (model != null && prices.containsKey(model)) {
            return prices.get(model);
        }
        return prices.get(defaultModel);
    }
}

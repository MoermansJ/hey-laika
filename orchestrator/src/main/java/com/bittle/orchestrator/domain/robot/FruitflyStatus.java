package com.bittle.orchestrator.domain.robot;

import java.util.Map;

public record FruitflyStatus(String robotId, String lastState, Map<String, Object> lastSignals) {
}

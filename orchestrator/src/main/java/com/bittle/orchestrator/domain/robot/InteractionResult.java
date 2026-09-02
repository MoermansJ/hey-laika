package com.bittle.orchestrator.domain.robot;

import java.util.Map;

public record InteractionResult(String robotId, String interaction,
                                Map<String, Object> personality) {
}

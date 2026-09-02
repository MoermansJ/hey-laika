package com.bittle.orchestrator.domain.robot;

public record DecisionModel(String engine, String model) {

    public static final DecisionModel UNKNOWN = new DecisionModel(null, null);

    public boolean isClaude() {
        return "claude".equals(engine) && model != null;
    }
}

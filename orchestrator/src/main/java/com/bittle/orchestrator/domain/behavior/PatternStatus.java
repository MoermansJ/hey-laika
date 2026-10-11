package com.bittle.orchestrator.domain.behavior;

/** Lifecycle of a {@link LearnedPattern} (AGENT_TOOL_COMPOSITION_DESIGN.md §2.2). */
public enum PatternStatus {

    ACTIVE("active"),
    INACTIVE("inactive"),
    DEPRECATED("deprecated");

    private final String wireId;

    PatternStatus(String wireId) {
        this.wireId = wireId;
    }

    public String wireId() {
        return wireId;
    }

    public static PatternStatus fromWireId(String id) {
        for (var status : values()) {
            if (status.wireId.equals(id)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown pattern status: " + id);
    }
}

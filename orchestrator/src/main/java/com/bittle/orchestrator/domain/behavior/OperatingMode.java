package com.bittle.orchestrator.domain.behavior;

public enum OperatingMode {

    STATIONARY("stationary"),
    ROAMING("roaming"),
    FRUITFLY("fruitfly"),
    PHONE("phone");

    private final String wireId;

    OperatingMode(String wireId) {
        this.wireId = wireId;
    }

    public String wireId() {
        return wireId;
    }

    public static OperatingMode fromWireId(String id) {
        for (var mode : values()) {
            if (mode.wireId.equals(id)) {
                return mode;
            }
        }
        throw new IllegalArgumentException("Unknown mode: " + id);
    }
}

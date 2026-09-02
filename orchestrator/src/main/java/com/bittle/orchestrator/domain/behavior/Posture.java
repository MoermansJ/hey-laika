package com.bittle.orchestrator.domain.behavior;

public enum Posture {
    STANDING,
    SITTING,
    LYING,
    SLEEPING;

    public boolean awake() {
        return this != SLEEPING;
    }
}

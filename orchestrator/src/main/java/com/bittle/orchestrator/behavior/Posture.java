package com.bittle.orchestrator.behavior;

/** Physical posture of the robot, tracked alongside personality state. */
public enum Posture {
    STANDING,
    SITTING,
    LYING,
    SLEEPING;

    public boolean awake() {
        return this != SLEEPING;
    }
}

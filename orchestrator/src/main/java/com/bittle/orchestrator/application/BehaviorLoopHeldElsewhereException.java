package com.bittle.orchestrator.application;

public class BehaviorLoopHeldElsewhereException extends RuntimeException {

    public BehaviorLoopHeldElsewhereException(String robotId, String holder) {
        super("The behavior loop for " + robotId + " is running on instance " + holder + ".");
    }
}

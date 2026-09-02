package com.bittle.orchestrator.application;

public class BehaviorLoopRunningException extends RuntimeException {

    public BehaviorLoopRunningException() {
        super("Stop the behavior loop before running a sequence.");
    }
}

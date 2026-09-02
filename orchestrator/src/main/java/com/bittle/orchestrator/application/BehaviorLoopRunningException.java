package com.bittle.orchestrator.application;

/**
 * Direct movement was requested while the behavior loop drives the robot;
 * the two would race on the servos.
 */
public class BehaviorLoopRunningException extends RuntimeException {

    public BehaviorLoopRunningException() {
        super("Stop the behavior loop before running a sequence.");
    }
}

package com.bittle.orchestrator.exception;

public class RobotNotFoundException extends RuntimeException {

    public RobotNotFoundException(String robotId) {
        super("No robot registered with id '" + robotId + "'");
    }
}

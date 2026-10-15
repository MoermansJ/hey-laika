package com.bittle.orchestrator.domain.behavior;

public class ActionNotFoundException extends RuntimeException {

    public ActionNotFoundException(String actionName) {
        super("No action registered with name '" + actionName + "'");
    }
}

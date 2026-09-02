package com.bittle.orchestrator.application.port.out;

public class AdapterUnavailableException extends RuntimeException {

    public AdapterUnavailableException(String serviceUrl, Throwable cause) {
        super("Robot adapter service unreachable: " + serviceUrl, cause);
    }
}

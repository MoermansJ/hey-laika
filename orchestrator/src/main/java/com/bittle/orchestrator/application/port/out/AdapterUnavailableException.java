package com.bittle.orchestrator.application.port.out;

/** The Python adapter service for a robot could not be reached. */
public class AdapterUnavailableException extends RuntimeException {

    public AdapterUnavailableException(String serviceUrl, Throwable cause) {
        super("Robot adapter service unreachable: " + serviceUrl, cause);
    }
}

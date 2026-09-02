package com.bittle.orchestrator.application.port.out;

public class AdapterErrorException extends RuntimeException {

    private final int status;
    private final String body;

    public AdapterErrorException(int status, String body) {
        super("Robot adapter returned HTTP " + status);
        this.status = status;
        this.body = body;
    }

    public int getStatus() { return status; }
    public String getBody() { return body; }
}

package com.bittle.orchestrator.application.port.out;

public interface EventPublisherPort {

    void publish(String topic, Object payload);
}

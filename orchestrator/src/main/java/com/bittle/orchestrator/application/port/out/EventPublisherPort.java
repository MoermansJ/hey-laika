package com.bittle.orchestrator.application.port.out;

/** Push channel to the dashboard. Topics are the UI contract (see docs/design). */
public interface EventPublisherPort {

    void publish(String topic, Object payload);
}

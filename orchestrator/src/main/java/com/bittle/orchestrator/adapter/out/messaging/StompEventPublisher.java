package com.bittle.orchestrator.adapter.out.messaging;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

@Component
public class StompEventPublisher implements EventPublisherPort {

    private final SimpMessagingTemplate messaging;

    public StompEventPublisher(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @Override
    public void publish(String topic, Object payload) {
        messaging.convertAndSend(topic, payload);
    }
}

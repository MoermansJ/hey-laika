package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.fleet.Robot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class BroadcastActivityUseCase {

    private static final Logger log = LoggerFactory.getLogger(BroadcastActivityUseCase.class);

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;
    private final EventPublisherPort publisher;

    public BroadcastActivityUseCase(FleetRegistry registry, RobotAdapterPort adapter,
                                    EventPublisherPort publisher) {
        this.registry = registry;
        this.adapter = adapter;
        this.publisher = publisher;
    }

    public void execute() {
        registry.all().forEach(this::publishQuietly);
    }

    private void publishQuietly(Robot robot) {
        try {
            publisher.publish("/topic/robot/" + robot.id() + "/activity", adapter.activity(robot));
        } catch (RuntimeException e) {
            log.debug("Skipping activity broadcast for {}: {}", robot.id(), e.getMessage());
        }
    }
}

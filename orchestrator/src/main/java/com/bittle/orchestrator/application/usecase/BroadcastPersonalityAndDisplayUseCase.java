package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class BroadcastPersonalityAndDisplayUseCase {

    private static final Logger log =
            LoggerFactory.getLogger(BroadcastPersonalityAndDisplayUseCase.class);

    private final Fleet fleet;
    private final RobotAdapterPort adapter;
    private final EventPublisherPort publisher;

    public BroadcastPersonalityAndDisplayUseCase(Fleet fleet, RobotAdapterPort adapter,
                                                 EventPublisherPort publisher) {
        this.fleet = fleet;
        this.adapter = adapter;
        this.publisher = publisher;
    }

    public void execute() {
        fleet.all().forEach(this::publishQuietly);
    }

    private void publishQuietly(Robot robot) {
        try {
            publisher.publish("/topic/robot/" + robot.id() + "/personality", adapter.personality(robot));
            publisher.publish("/topic/robot/" + robot.id() + "/display", adapter.display(robot));
        } catch (RuntimeException e) {
            log.debug("Skipping personality/display broadcast for {}: {}", robot.id(), e.getMessage());
        }
    }
}

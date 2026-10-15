package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Observability only (PERSONALITY_MODES_BRIEF.md §3.3/§7c): polls
 * fruitfly_drive.py's last decoded command and rebroadcasts it for the
 * Mind/Fruitfly GUI card, same shape as {@link BroadcastActivityUseCase}.
 * This never drives anything — the arbiter submission already happened
 * on the adapter side by the time this reads it.
 */
public class BroadcastFruitflyUseCase {

    private static final Logger log = LoggerFactory.getLogger(BroadcastFruitflyUseCase.class);

    private final Fleet fleet;
    private final RobotAdapterPort adapter;
    private final EventPublisherPort publisher;

    public BroadcastFruitflyUseCase(Fleet fleet, RobotAdapterPort adapter,
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
            publisher.publish("/topic/robot/" + robot.id() + "/fruitfly", adapter.fruitflyStatus(robot));
        } catch (RuntimeException e) {
            log.debug("Skipping fruitfly broadcast for {}: {}", robot.id(), e.getMessage());
        }
    }
}

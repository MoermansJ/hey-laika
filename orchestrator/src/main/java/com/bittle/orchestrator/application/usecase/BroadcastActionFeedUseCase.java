package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Pushes the adapter's per-action feed out on {@code /topic/robot/{id}/actions}
 * so the console sees each generated action as it happens, rather than polling
 * for it. Same poll-and-rebroadcast shape as {@link BroadcastActivityUseCase},
 * but on a faster sweep: actions land about once a second while a mode is
 * driving, so a 4-5s sweep would collapse several of them into one update.
 */
public class BroadcastActionFeedUseCase {

    private static final Logger log = LoggerFactory.getLogger(BroadcastActionFeedUseCase.class);

    private final Fleet fleet;
    private final RobotAdapterPort adapter;
    private final EventPublisherPort publisher;

    public BroadcastActionFeedUseCase(Fleet fleet, RobotAdapterPort adapter,
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
            publisher.publish("/topic/robot/" + robot.id() + "/actions", adapter.actionFeed(robot));
        } catch (RuntimeException e) {
            log.debug("Skipping action feed broadcast for {}: {}", robot.id(), e.getMessage());
        }
    }
}

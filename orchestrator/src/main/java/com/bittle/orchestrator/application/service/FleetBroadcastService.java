package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.in.FleetBroadcastUseCase;
import com.bittle.orchestrator.application.port.in.FleetUseCase;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.FleetStats;
import com.bittle.orchestrator.domain.fleet.Robot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Decides what fleet and robot state goes to which dashboard topic. */
public class FleetBroadcastService implements FleetBroadcastUseCase {

    private static final Logger log = LoggerFactory.getLogger(FleetBroadcastService.class);

    private final FleetRegistry registry;
    private final FleetUseCase fleet;
    private final RobotAdapterPort adapter;
    private final EventPublisherPort publisher;

    public FleetBroadcastService(FleetRegistry registry, FleetUseCase fleet,
                                 RobotAdapterPort adapter, EventPublisherPort publisher) {
        this.registry = registry;
        this.fleet = fleet;
        this.adapter = adapter;
        this.publisher = publisher;
    }

    @Override
    public void broadcastStatus() {
        if (registry.all().isEmpty()) {
            return;
        }
        var statuses = fleet.fleetStatus();
        publisher.publish("/topic/fleet/status", statuses);
        statuses.forEach((id, status) -> publisher.publish("/topic/robot/" + id + "/status", status));
        publisher.publish("/topic/fleet/stats", FleetStats.of(statuses.values()));
    }

    @Override
    public void broadcastPersonalityAndDisplay() {
        registry.all().forEach(robot -> publishQuietly(robot, "personality/display", () -> {
            publisher.publish(robotTopic(robot, "personality"), adapter.personality(robot));
            publisher.publish(robotTopic(robot, "display"), adapter.display(robot));
        }));
    }

    @Override
    public void broadcastActivity() {
        registry.all().forEach(robot -> publishQuietly(robot, "activity", () ->
                publisher.publish(robotTopic(robot, "activity"), adapter.activity(robot))));
    }

    private static String robotTopic(Robot robot, String suffix) {
        return "/topic/robot/" + robot.id() + "/" + suffix;
    }

    private static void publishQuietly(Robot robot, String what, Runnable publish) {
        try {
            publish.run();
        } catch (RuntimeException e) {
            log.debug("Skipping {} broadcast for {}: {}", what, robot.id(), e.getMessage());
        }
    }
}

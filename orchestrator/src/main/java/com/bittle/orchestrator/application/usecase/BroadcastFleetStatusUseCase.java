package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.fleet.FleetStats;

public class BroadcastFleetStatusUseCase {

    private final FleetRegistry registry;
    private final GetFleetStatusUseCase fleetStatus;
    private final EventPublisherPort publisher;

    public BroadcastFleetStatusUseCase(FleetRegistry registry, GetFleetStatusUseCase fleetStatus,
                                       EventPublisherPort publisher) {
        this.registry = registry;
        this.fleetStatus = fleetStatus;
        this.publisher = publisher;
    }

    public void execute() {
        if (registry.all().isEmpty()) {
            return;
        }
        var statuses = fleetStatus.execute();
        publisher.publish("/topic/fleet/status", statuses);
        statuses.forEach((id, status) -> publisher.publish("/topic/robot/" + id + "/status", status));
        publisher.publish("/topic/fleet/stats", FleetStats.of(statuses.values()));
    }
}

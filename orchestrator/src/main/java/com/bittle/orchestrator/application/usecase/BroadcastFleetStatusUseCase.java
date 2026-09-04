package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.FleetStats;

public class BroadcastFleetStatusUseCase {

    private final Fleet fleet;
    private final GetFleetStatusUseCase fleetStatus;
    private final EventPublisherPort publisher;

    public BroadcastFleetStatusUseCase(Fleet fleet, GetFleetStatusUseCase fleetStatus,
                                       EventPublisherPort publisher) {
        this.fleet = fleet;
        this.fleetStatus = fleetStatus;
        this.publisher = publisher;
    }

    public void execute() {
        if (fleet.all().isEmpty()) {
            return;
        }
        var statuses = fleetStatus.execute();
        publisher.publish("/topic/fleet/status", statuses);
        statuses.forEach((id, status) -> publisher.publish("/topic/robot/" + id + "/status", status));
        publisher.publish("/topic/fleet/stats", FleetStats.of(statuses.values()));
    }
}

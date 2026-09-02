package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.domain.fleet.FleetStats;

public class GetFleetStatsUseCase {

    private final GetFleetStatusUseCase fleetStatus;

    public GetFleetStatsUseCase(GetFleetStatusUseCase fleetStatus) {
        this.fleetStatus = fleetStatus;
    }

    public FleetStats execute() {
        return FleetStats.of(fleetStatus.execute().values());
    }
}

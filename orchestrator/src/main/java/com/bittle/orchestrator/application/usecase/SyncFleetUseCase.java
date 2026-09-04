package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.FleetRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SyncFleetUseCase {

    private static final Logger log = LoggerFactory.getLogger(SyncFleetUseCase.class);

    private final Fleet fleet;
    private final FleetRepositoryPort repository;

    public SyncFleetUseCase(Fleet fleet, FleetRepositoryPort repository) {
        this.fleet = fleet;
        this.repository = repository;
    }

    public void execute() {
        var configuredIds = fleet.all().stream().map(Robot::id).toList();
        repository.deactivateAllExcept(configuredIds).forEach(id ->
                log.info("Robot {} no longer configured; marked inactive", id));

        fleet.all().forEach(robot -> {
            repository.upsertActive(robot);
            log.info("Configured robot {} ({}) -> {}", robot.id(), robot.name(), robot.serviceUrl());
        });

        log.info("Fleet initialized with {} active robot(s)", fleet.all().size());
    }
}

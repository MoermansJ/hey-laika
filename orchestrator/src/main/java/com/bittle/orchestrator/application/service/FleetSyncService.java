package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.in.SyncFleetUseCase;
import com.bittle.orchestrator.application.port.out.FleetRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Reconciles the configured robot list with the database and the live registry. */
public class FleetSyncService implements SyncFleetUseCase {

    private static final Logger log = LoggerFactory.getLogger(FleetSyncService.class);

    private final FleetRegistry registry;
    private final FleetRepositoryPort repository;

    public FleetSyncService(FleetRegistry registry, FleetRepositoryPort repository) {
        this.registry = registry;
        this.repository = repository;
    }

    @Override
    public void sync(List<Robot> configured) {
        var configuredIds = configured.stream().map(Robot::id).toList();
        repository.deactivateAllExcept(configuredIds).forEach(id ->
                log.info("Robot {} no longer configured; marked inactive", id));

        configured.forEach(robot -> {
            repository.upsertActive(robot);
            registry.register(robot);
            log.info("Registered robot {} ({}) -> {}", robot.id(), robot.name(), robot.serviceUrl());
        });

        log.info("Fleet initialized with {} active robot(s)", registry.all().size());
    }
}

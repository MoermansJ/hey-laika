package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.FleetRepositoryPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SyncFleetUseCase {

    private static final Logger log = LoggerFactory.getLogger(SyncFleetUseCase.class);

    private final FleetRegistry registry;
    private final FleetRepositoryPort repository;

    public SyncFleetUseCase(FleetRegistry registry, FleetRepositoryPort repository) {
        this.registry = registry;
        this.repository = repository;
    }

    public void execute(List<Robot> configured) {
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

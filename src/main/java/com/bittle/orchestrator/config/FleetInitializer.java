package com.bittle.orchestrator.config;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.client.PythonServiceClient;
import com.bittle.orchestrator.fleet.FleetManager;
import com.bittle.orchestrator.model.RobotEntity;
import com.bittle.orchestrator.repository.RobotRepository;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * Syncs the configured robot list into the fleet database and registers a
 * live agent for each robot. Robots that disappear from configuration are
 * kept in the database (history) but marked inactive and not registered.
 */
@Component
public class FleetInitializer implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(FleetInitializer.class);

    private final RobotsProperties properties;
    private final RobotRepository repository;
    private final FleetManager fleetManager;
    private final PythonServiceClient pythonClient;

    public FleetInitializer(RobotsProperties properties, RobotRepository repository,
                            FleetManager fleetManager, PythonServiceClient pythonClient) {
        this.properties = properties;
        this.repository = repository;
        this.fleetManager = fleetManager;
        this.pythonClient = pythonClient;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        var configured = properties.robots() == null ? java.util.List.<RobotsProperties.RobotDefinition>of()
                                                     : properties.robots();

        var configuredIds = configured.stream().map(RobotsProperties.RobotDefinition::id).toList();
        repository.findAll().stream()
                .filter(entity -> !configuredIds.contains(entity.getRobotId()))
                .forEach(entity -> {
                    entity.setActive(false);
                    repository.save(entity);
                    log.info("Robot {} no longer configured; marked inactive", entity.getRobotId());
                });

        for (var definition : configured) {
            var entity = repository.findByRobotId(definition.id()).orElseGet(RobotEntity::new);
            var isNew = entity.getId() == null;
            entity.setRobotId(definition.id());
            entity.setName(definition.name());
            entity.setType(definition.type());
            entity.setServiceUrl(definition.serviceUrl());
            entity.setActive(true);
            if (isNew) {
                entity.setCreatedAt(Instant.now());
            }
            entity.setUpdatedAt(Instant.now());
            repository.save(entity);

            fleetManager.register(new RobotAgent(definition, pythonClient));
            log.info("Registered robot {} ({}) -> {}", definition.id(), definition.name(),
                     definition.serviceUrl());
        }

        log.info("Fleet initialized with {} active robot(s)", fleetManager.all().size());
    }
}

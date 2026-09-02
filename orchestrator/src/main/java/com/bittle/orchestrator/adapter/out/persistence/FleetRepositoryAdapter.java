package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.FleetRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** JPA-backed fleet metadata. Each call is its own transaction. */
@Component
public class FleetRepositoryAdapter implements FleetRepositoryPort {

    private final RobotJpaRepository repository;

    public FleetRepositoryAdapter(RobotJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional
    public void upsertActive(Robot robot) {
        var entity = repository.findByRobotId(robot.id()).orElseGet(RobotEntity::new);
        var isNew = entity.getId() == null;
        entity.setRobotId(robot.id());
        entity.setName(robot.name());
        entity.setType(robot.type());
        entity.setServiceUrl(robot.serviceUrl());
        entity.setActive(true);
        if (isNew) {
            entity.setCreatedAt(Instant.now());
        }
        entity.setUpdatedAt(Instant.now());
        repository.save(entity);
    }

    @Override
    @Transactional
    public List<String> deactivateAllExcept(Collection<String> ids) {
        var stale = repository.findAll().stream()
                .filter(entity -> !ids.contains(entity.getRobotId()))
                .toList();
        stale.forEach(entity -> {
            entity.setActive(false);
            repository.save(entity);
        });
        return stale.stream().map(RobotEntity::getRobotId).toList();
    }
}

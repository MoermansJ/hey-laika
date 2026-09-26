package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class RobotModeRepositoryAdapter implements RobotModeRepositoryPort {

    private final RobotModeJpaRepository repository;

    public RobotModeRepositoryAdapter(RobotModeJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<RobotMode> find(String robotId) {
        return repository.findById(robotId).map(RobotModeRepositoryAdapter::toDomain);
    }

    @Override
    @Transactional
    public void save(RobotMode mode) {
        var entity = repository.findById(mode.robotId()).orElseGet(RobotModeEntity::new);
        entity.setRobotId(mode.robotId());
        entity.setMode(mode.mode().wireId());
        entity.setChangedAt(mode.changedAt());
        entity.setChangedBy(mode.changedBy());
        repository.save(entity);
    }

    private static RobotMode toDomain(RobotModeEntity entity) {
        return new RobotMode(entity.getRobotId(), OperatingMode.fromWireId(entity.getMode()),
                entity.getChangedAt(), entity.getChangedBy());
    }
}

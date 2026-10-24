package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.RobotIntroductionRepositoryPort;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class RobotIntroductionRepositoryAdapter implements RobotIntroductionRepositoryPort {

    private final RobotIntroductionJpaRepository repository;

    public RobotIntroductionRepositoryAdapter(RobotIntroductionJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<RobotIntroduction> find(String robotId) {
        return repository.findById(robotId).map(RobotIntroductionRepositoryAdapter::toDomain);
    }

    @Override
    @Transactional
    public void save(RobotIntroduction introduction) {
        var entity = repository.findById(introduction.robotId())
                .orElseGet(RobotIntroductionEntity::new);
        entity.setRobotId(introduction.robotId());
        entity.setIntroduction(introduction.text());
        entity.setUpdatedAt(introduction.updatedAt());
        entity.setUpdatedBy(introduction.updatedBy());
        repository.save(entity);
    }

    private static RobotIntroduction toDomain(RobotIntroductionEntity entity) {
        return new RobotIntroduction(entity.getRobotId(), entity.getIntroduction(),
                entity.getUpdatedAt(), entity.getUpdatedBy());
    }
}

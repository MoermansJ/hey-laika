package com.bittle.orchestrator.adapter.out.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface RobotIntroductionJpaRepository
        extends JpaRepository<RobotIntroductionEntity, String> {
}

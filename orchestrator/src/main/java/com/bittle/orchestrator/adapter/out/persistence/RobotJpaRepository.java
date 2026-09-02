package com.bittle.orchestrator.adapter.out.persistence;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RobotJpaRepository extends JpaRepository<RobotEntity, Long> {

    Optional<RobotEntity> findByRobotId(String robotId);
}

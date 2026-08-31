package com.bittle.orchestrator.repository;

import com.bittle.orchestrator.model.RobotEntity;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RobotRepository extends JpaRepository<RobotEntity, Long> {

    Optional<RobotEntity> findByRobotId(String robotId);
}

package com.bittle.orchestrator.adapter.out.persistence;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MetricsRollupJpaRepository extends JpaRepository<MetricsRollupEntity, Long> {

    List<MetricsRollupEntity> findByRobotIdOrderByHourStartDesc(String robotId, Pageable pageable);
}

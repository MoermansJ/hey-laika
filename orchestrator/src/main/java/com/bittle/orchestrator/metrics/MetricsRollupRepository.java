package com.bittle.orchestrator.metrics;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MetricsRollupRepository extends JpaRepository<MetricsRollup, Long> {

    List<MetricsRollup> findByRobotIdOrderByHourStartDesc(String robotId, Pageable pageable);
}

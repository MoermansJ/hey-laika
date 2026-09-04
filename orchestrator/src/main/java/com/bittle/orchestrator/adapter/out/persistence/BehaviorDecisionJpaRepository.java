package com.bittle.orchestrator.adapter.out.persistence;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface BehaviorDecisionJpaRepository extends JpaRepository<BehaviorDecisionEntity, Long> {

    List<BehaviorDecisionEntity> findByRobotIdOrderByIdDesc(String robotId, Pageable pageable);

    @Modifying
    @Transactional
    @Query("delete from BehaviorDecisionEntity d where d.robotId = :robotId and d.id <= :maxId")
    int deleteUpTo(@Param("robotId") String robotId, @Param("maxId") long maxId);
}

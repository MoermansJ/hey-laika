package com.bittle.orchestrator.adapter.out.persistence;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * Method names follow the design's repository (§2.1). The outcome lives in flat
 * columns, so "outcome not null" is expressed as an explicit query on its
 * presence marker {@code outcomeEvaluatedAt}.
 */
public interface BehaviorRunLogJpaRepository extends JpaRepository<BehaviorRunLogEntity, UUID> {

    List<BehaviorRunLogEntity> findByRobotIdAndSourceOrderByRunTimestampDesc(String robotId, String source);

    @Query("select r from BehaviorRunLogEntity r where r.robotId = :robotId and r.goal = :goal"
            + " and r.outcomeEvaluatedAt is not null order by r.runTimestamp desc")
    List<BehaviorRunLogEntity> findByRobotIdAndGoalAndOutcomeNotNull(@Param("robotId") String robotId,
                                                                     @Param("goal") String goal);

    @Query("select r from BehaviorRunLogEntity r where r.robotId = :robotId and r.source = :source"
            + " and r.outcomeEvaluatedAt is not null order by r.runTimestamp desc")
    List<BehaviorRunLogEntity> findByRobotIdAndSourceAndOutcomeIsNotNull(@Param("robotId") String robotId,
                                                                         @Param("source") String source);
}

package com.bittle.orchestrator.adapter.out.persistence;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** Query methods follow the design's repository (§2.2); status is its wire id. */
public interface LearnedPatternJpaRepository extends JpaRepository<LearnedPatternEntity, UUID> {

    List<LearnedPatternEntity> findByRobotIdAndGoal(String robotId, String goal);

    List<LearnedPatternEntity> findByRobotIdAndGoalOrderBySuccessRateDescAttemptsDesc(String robotId,
                                                                                    String goal);

    List<LearnedPatternEntity> findByRobotIdAndStatus(String robotId, String status);

    Optional<LearnedPatternEntity> findByRobotIdAndGoalAndToolCombinationJson(String robotId, String goal,
                                                                             String toolCombinationJson);
}

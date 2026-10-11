package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface BehaviorRunLogRepositoryPort {

    BehaviorRunLog save(BehaviorRunLog runLog);

    Optional<BehaviorRunLog> findById(UUID id);

    /** Newest first. */
    List<BehaviorRunLog> findByRobotIdAndSource(String robotId, String source);

    /** Runs for a goal that already carry an outcome evaluation, newest first. */
    List<BehaviorRunLog> findByRobotIdAndGoalWithOutcome(String robotId, String goal);

    /** Runs from a source (e.g. "agent") that already carry an outcome evaluation, newest first. */
    List<BehaviorRunLog> findByRobotIdAndSourceWithOutcome(String robotId, String source);

    /** Attaches an outcome to an existing run; empty when no run has that id. */
    Optional<BehaviorRunLog> attachOutcome(UUID id, OutcomeEvaluation outcome);
}

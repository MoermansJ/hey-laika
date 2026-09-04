package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import java.util.List;

public interface DecisionHistoryRepositoryPort {

    void append(BehaviorDecision decision);

    List<BehaviorDecision> findLatest(String robotId, int limit);

    void trim(String robotId, int keep);
}

package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.DecisionHistoryRepositoryPort;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision.DecisionSource;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class DecisionHistoryRepositoryAdapter implements DecisionHistoryRepositoryPort {

    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {
    };

    private final BehaviorDecisionJpaRepository repository;
    private final ObjectMapper objectMapper;

    public DecisionHistoryRepositoryAdapter(BehaviorDecisionJpaRepository repository,
                                            ObjectMapper objectMapper) {
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    @Override
    @Transactional
    public void append(BehaviorDecision decision) {
        var entity = new BehaviorDecisionEntity();
        entity.setRobotId(decision.robotId());
        entity.setDecidedAt(decision.decidedAt());
        entity.setSelectedAction(decision.selectedAction());
        entity.setSource(decision.source() == null ? null : decision.source().name());
        entity.setReasoning(decision.reasoning());
        entity.setSuccess(decision.success());
        entity.setActualDurationMs(decision.actualDurationMs());
        entity.setStateJson(write(decision.stateAtDecision()));
        entity.setValidActionsJson(write(decision.validActions()));
        repository.save(entity);
    }

    @Override
    @Transactional(readOnly = true)
    public List<BehaviorDecision> findLatest(String robotId, int limit) {
        if (limit <= 0) {
            return List.of();
        }
        return repository.findByRobotIdOrderByIdDesc(robotId, PageRequest.of(0, limit)).stream()
                .map(this::toDecision)
                .toList();
    }

    @Override
    @Transactional
    public void trim(String robotId, int keep) {
        var oldestKept = repository.findByRobotIdOrderByIdDesc(robotId, PageRequest.of(keep, 1));
        if (!oldestKept.isEmpty()) {
            repository.deleteUpTo(robotId, oldestKept.get(0).getId());
        }
    }

    private BehaviorDecision toDecision(BehaviorDecisionEntity entity) {
        return new BehaviorDecision(entity.getRobotId(), entity.getDecidedAt(),
                read(entity.getStateJson(), PersonalityState.Snapshot.class),
                read(entity.getValidActionsJson(), STRING_LIST),
                entity.getSelectedAction(),
                entity.getSource() == null ? null : DecisionSource.valueOf(entity.getSource()),
                entity.getReasoning(), entity.getSuccess(), entity.getActualDurationMs());
    }

    private String write(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Decision not serializable", e);
        }
    }

    private <T> T read(String json, Class<T> type) {
        try {
            return objectMapper.readValue(json, type);
        } catch (JsonProcessingException e) {
            return null;
        }
    }

    private <T> T read(String json, TypeReference<T> type) {
        try {
            return objectMapper.readValue(json, type);
        } catch (JsonProcessingException e) {
            return null;
        }
    }
}

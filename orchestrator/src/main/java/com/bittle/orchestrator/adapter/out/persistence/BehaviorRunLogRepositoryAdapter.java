package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.BehaviorRunLogRepositoryPort;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class BehaviorRunLogRepositoryAdapter implements BehaviorRunLogRepositoryPort {

    private static final TypeReference<Map<String, Object>> JSON_MAP = new TypeReference<>() {
    };

    private final BehaviorRunLogJpaRepository repository;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Autowired
    public BehaviorRunLogRepositoryAdapter(BehaviorRunLogJpaRepository repository,
                                           ObjectMapper objectMapper) {
        this(repository, objectMapper, Clock.systemUTC());
    }

    BehaviorRunLogRepositoryAdapter(BehaviorRunLogJpaRepository repository,
                                    ObjectMapper objectMapper, Clock clock) {
        this.repository = repository;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Override
    @Transactional
    public BehaviorRunLog save(BehaviorRunLog runLog) {
        return toDomain(repository.save(toEntity(runLog)));
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<BehaviorRunLog> findById(UUID id) {
        return repository.findById(id).map(this::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public List<BehaviorRunLog> findByRobotIdAndSource(String robotId, String source) {
        return toDomain(repository.findByRobotIdAndSourceOrderByRunTimestampDesc(robotId, source));
    }

    @Override
    @Transactional(readOnly = true)
    public List<BehaviorRunLog> findByRobotIdAndGoalWithOutcome(String robotId, String goal) {
        return toDomain(repository.findByRobotIdAndGoalAndOutcomeNotNull(robotId, goal));
    }

    @Override
    @Transactional(readOnly = true)
    public List<BehaviorRunLog> findByRobotIdAndSourceWithOutcome(String robotId, String source) {
        return toDomain(repository.findByRobotIdAndSourceAndOutcomeIsNotNull(robotId, source));
    }

    @Override
    @Transactional
    public Optional<BehaviorRunLog> attachOutcome(UUID id, OutcomeEvaluation outcome) {
        return repository.findById(id).map(entity -> {
            applyOutcome(entity, outcome);
            entity.setUpdatedAt(clock.instant());
            return toDomain(repository.save(entity));
        });
    }

    private List<BehaviorRunLog> toDomain(List<BehaviorRunLogEntity> entities) {
        return entities.stream().map(this::toDomain).toList();
    }

    private BehaviorRunLogEntity toEntity(BehaviorRunLog run) {
        var entity = new BehaviorRunLogEntity();
        entity.setId(run.id());
        entity.setRobotId(run.robotId());
        entity.setRunTimestamp(run.timestamp());
        entity.setCompletedAt(run.completedAt());
        entity.setBehaviorName(run.behaviorName());
        entity.setSource(run.source());
        entity.setPriority(run.priority());
        entity.setCauseJson(write(run.cause()));
        entity.setExecutionTimeMs(run.executionTimeMs());
        entity.setPreemptedBy(run.preemptedBy());
        entity.setGoal(run.goal());
        entity.setSensorDeltaJson(write(run.sensorDelta()));
        applyOutcome(entity, run.outcome());
        var now = clock.instant();
        entity.setCreatedAt(run.createdAt() == null ? now : run.createdAt());
        entity.setUpdatedAt(run.updatedAt() == null ? now : run.updatedAt());
        return entity;
    }

    private static void applyOutcome(BehaviorRunLogEntity entity, OutcomeEvaluation outcome) {
        entity.setOutcomeSuccess(outcome == null ? null : outcome.success());
        entity.setOutcomeConfidence(outcome == null ? null : outcome.confidence());
        entity.setOutcomeReason(outcome == null ? null : outcome.reason());
        entity.setOutcomeEvaluatorVersion(outcome == null ? null : outcome.evaluatorVersion());
        entity.setOutcomeEvaluatedAt(outcome == null ? null : outcome.evaluatedAt());
    }

    private BehaviorRunLog toDomain(BehaviorRunLogEntity e) {
        // The evaluatedAt column marks an outcome as present; rows without it
        // (non-agent runs, rows written before evaluation) read back as null.
        var outcome = e.getOutcomeEvaluatedAt() == null ? null
                : new OutcomeEvaluation(e.getOutcomeSuccess(), e.getOutcomeConfidence(),
                        e.getOutcomeReason(), e.getOutcomeEvaluatorVersion(),
                        e.getOutcomeEvaluatedAt());
        return new BehaviorRunLog(e.getId(), e.getRobotId(), e.getRunTimestamp(), e.getCompletedAt(),
                e.getBehaviorName(), e.getSource(), e.getPriority(), read(e.getCauseJson()),
                e.getExecutionTimeMs(), e.getPreemptedBy(), e.getGoal(), outcome,
                read(e.getSensorDeltaJson()), e.getCreatedAt(), e.getUpdatedAt());
    }

    private String write(Map<String, Object> value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Run-log field not serializable", e);
        }
    }

    private Map<String, Object> read(String json) {
        if (json == null) {
            return null;
        }
        try {
            return objectMapper.readValue(json, JSON_MAP);
        } catch (JsonProcessingException e) {
            return null;
        }
    }
}

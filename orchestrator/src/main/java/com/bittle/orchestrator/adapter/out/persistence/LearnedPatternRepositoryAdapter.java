package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.LearnedPatternRepositoryPort;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.PatternStatus;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class LearnedPatternRepositoryAdapter implements LearnedPatternRepositoryPort {

    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {
    };

    private final LearnedPatternJpaRepository repository;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Autowired
    public LearnedPatternRepositoryAdapter(LearnedPatternJpaRepository repository,
                                           ObjectMapper objectMapper) {
        this(repository, objectMapper, Clock.systemUTC());
    }

    LearnedPatternRepositoryAdapter(LearnedPatternJpaRepository repository,
                                    ObjectMapper objectMapper, Clock clock) {
        this.repository = repository;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Override
    @Transactional
    public LearnedPattern save(LearnedPattern pattern) {
        return toDomain(repository.save(toEntity(pattern)));
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<LearnedPattern> findById(UUID id) {
        return repository.findById(id).map(this::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public List<LearnedPattern> findByRobotIdAndGoal(String robotId, String goal) {
        return toDomain(repository.findByRobotIdAndGoal(robotId, goal));
    }

    @Override
    @Transactional(readOnly = true)
    public List<LearnedPattern> findByRobotIdAndGoalOrderBySuccessRateDesc(String robotId, String goal) {
        return toDomain(repository.findByRobotIdAndGoalOrderBySuccessRateDescAttemptsDesc(robotId, goal));
    }

    @Override
    @Transactional(readOnly = true)
    public List<LearnedPattern> findByRobotIdAndStatus(String robotId, PatternStatus status) {
        return toDomain(repository.findByRobotIdAndStatus(robotId, status.wireId()));
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<LearnedPattern> findByRobotIdAndGoalAndToolCombination(String robotId, String goal,
                                                                            List<String> toolCombination) {
        return repository.findByRobotIdAndGoalAndToolCombinationJson(robotId, goal, write(toolCombination))
                .map(this::toDomain);
    }

    private List<LearnedPattern> toDomain(List<LearnedPatternEntity> entities) {
        return entities.stream().map(this::toDomain).toList();
    }

    private LearnedPatternEntity toEntity(LearnedPattern p) {
        var entity = new LearnedPatternEntity();
        entity.setId(p.id());
        entity.setRobotId(p.robotId());
        entity.setGoal(p.goal());
        entity.setToolCombinationJson(write(p.toolCombination()));
        entity.setAttempts(p.attempts());
        entity.setSuccesses(p.successes());
        entity.setSuccessRate(p.successRate());
        entity.setFirstDiscovered(p.firstDiscovered());
        entity.setLastUsed(p.lastUsed());
        entity.setStatus(p.status().wireId());
        var now = clock.instant();
        entity.setCreatedAt(p.createdAt() == null ? now : p.createdAt());
        entity.setUpdatedAt(p.updatedAt() == null ? now : p.updatedAt());
        return entity;
    }

    private LearnedPattern toDomain(LearnedPatternEntity e) {
        return new LearnedPattern(e.getId(), e.getRobotId(), e.getGoal(), read(e.getToolCombinationJson()),
                e.getAttempts(), e.getSuccesses(), e.getSuccessRate(), e.getFirstDiscovered(),
                e.getLastUsed(), PatternStatus.fromWireId(e.getStatus()), e.getCreatedAt(),
                e.getUpdatedAt());
    }

    /** Canonical key text: a compact JSON array, so equal ordered lists give equal strings. */
    String write(List<String> toolCombination) {
        try {
            return objectMapper.writeValueAsString(List.copyOf(toolCombination));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Tool combination not serializable", e);
        }
    }

    private List<String> read(String json) {
        try {
            return objectMapper.readValue(json, STRING_LIST);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Stored tool combination is not a JSON string array", e);
        }
    }
}

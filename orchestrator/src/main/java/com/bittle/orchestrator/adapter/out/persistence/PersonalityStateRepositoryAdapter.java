package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.PersonalityStateRepositoryPort;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.bittle.orchestrator.domain.behavior.Posture;
import java.time.Instant;
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class PersonalityStateRepositoryAdapter implements PersonalityStateRepositoryPort {

    private final PersonalityStateJpaRepository repository;

    public PersonalityStateRepositoryAdapter(PersonalityStateJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<PersonalityState.Snapshot> find(String robotId) {
        return repository.findById(robotId).map(PersonalityStateRepositoryAdapter::toSnapshot);
    }

    @Override
    @Transactional
    public void save(PersonalityState.Snapshot snapshot) {
        var entity = repository.findById(snapshot.robotId()).orElseGet(PersonalityStateEntity::new);
        entity.setRobotId(snapshot.robotId());
        entity.setEnergy(snapshot.energy());
        entity.setHappiness(snapshot.happiness());
        entity.setBoredom(snapshot.boredom());
        entity.setCuriosity(snapshot.curiosity());
        entity.setHunger(snapshot.hunger());
        entity.setContentment(snapshot.contentment());
        entity.setPosture(snapshot.posture() == null ? null : snapshot.posture().name());
        entity.setLastAction(snapshot.lastAction());
        entity.setLastActionAt(snapshot.lastActionAt());
        entity.setLastInteractionAt(snapshot.lastInteractionAt());
        entity.setTotalActions(snapshot.totalActionsThisSession());
        entity.setUpdatedAt(Instant.now());
        repository.save(entity);
    }

    private static PersonalityState.Snapshot toSnapshot(PersonalityStateEntity entity) {
        return new PersonalityState.Snapshot(entity.getRobotId(), entity.getEnergy(),
                entity.getHappiness(), entity.getBoredom(), entity.getCuriosity(),
                entity.getHunger(), entity.getContentment(),
                entity.getPosture() == null ? Posture.STANDING : Posture.valueOf(entity.getPosture()),
                entity.getLastAction(), entity.getLastActionAt(), entity.getLastInteractionAt(),
                entity.getTotalActions());
    }
}

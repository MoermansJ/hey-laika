package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.behavior.PersonalityState;
import java.util.Optional;

public interface PersonalityStateRepositoryPort {

    Optional<PersonalityState.Snapshot> find(String robotId);

    void save(PersonalityState.Snapshot snapshot);
}

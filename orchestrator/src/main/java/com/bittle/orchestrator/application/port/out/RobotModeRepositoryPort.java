package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.behavior.RobotMode;
import java.util.Optional;

public interface RobotModeRepositoryPort {

    Optional<RobotMode> find(String robotId);

    void save(RobotMode mode);
}

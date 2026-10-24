package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import java.util.Optional;

public interface RobotIntroductionRepositoryPort {

    Optional<RobotIntroduction> find(String robotId);

    void save(RobotIntroduction introduction);
}

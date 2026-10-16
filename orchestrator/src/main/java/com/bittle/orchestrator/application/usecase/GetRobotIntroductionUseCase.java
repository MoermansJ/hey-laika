package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotIntroductionRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;

public class GetRobotIntroductionUseCase {

    private final Fleet fleet;
    private final RobotIntroductionRepositoryPort introductions;

    public GetRobotIntroductionUseCase(Fleet fleet,
                                       RobotIntroductionRepositoryPort introductions) {
        this.fleet = fleet;
        this.introductions = introductions;
    }

    /**
     * The stored row, or an empty one when nothing has been written yet — in
     * which case the adapter is still speaking its compiled default. Reads
     * never write: no row is seeded here.
     */
    public RobotIntroduction execute(String robotId) {
        var robot = fleet.get(robotId);
        return introductions.find(robot.id()).orElseGet(() -> RobotIntroduction.none(robot.id()));
    }
}

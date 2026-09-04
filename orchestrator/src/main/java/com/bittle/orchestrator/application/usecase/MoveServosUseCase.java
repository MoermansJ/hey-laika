package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.ServoMoveRequest;
import com.bittle.orchestrator.domain.robot.ServoMoveResult;

public class MoveServosUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public MoveServosUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public ServoMoveResult execute(String robotId, ServoMoveRequest request) {
        return adapter.moveServos(fleet.get(robotId), request);
    }
}

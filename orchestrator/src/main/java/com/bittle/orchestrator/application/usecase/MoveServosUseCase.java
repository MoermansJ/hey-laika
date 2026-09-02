package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.ServoMoveRequest;
import com.bittle.orchestrator.domain.robot.ServoMoveResult;

public class MoveServosUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public MoveServosUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public ServoMoveResult execute(String robotId, ServoMoveRequest request) {
        return adapter.moveServos(registry.get(robotId), request);
    }
}

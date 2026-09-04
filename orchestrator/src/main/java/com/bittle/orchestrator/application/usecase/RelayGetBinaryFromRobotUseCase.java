package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.BinaryContent;

public class RelayGetBinaryFromRobotUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public RelayGetBinaryFromRobotUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public BinaryContent execute(String robotId, String path) {
        return adapter.getBinary(fleet.get(robotId), path);
    }
}

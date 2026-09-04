package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.AnimationList;

public class ListAnimationsUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public ListAnimationsUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public AnimationList execute(String robotId) {
        return adapter.animations(fleet.get(robotId));
    }
}

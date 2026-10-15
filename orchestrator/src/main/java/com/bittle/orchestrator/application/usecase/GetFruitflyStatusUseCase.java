package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.FruitflyStatus;

public class GetFruitflyStatusUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetFruitflyStatusUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public FruitflyStatus execute(String robotId) {
        return adapter.fruitflyStatus(fleet.get(robotId));
    }
}

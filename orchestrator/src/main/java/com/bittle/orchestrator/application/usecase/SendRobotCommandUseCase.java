package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.CommandResult;

public class SendRobotCommandUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public SendRobotCommandUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public CommandResult execute(String robotId, String command) {
        return adapter.command(fleet.get(robotId), command);
    }
}

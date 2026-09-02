package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.CommandResult;

public class SendRobotCommandUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public SendRobotCommandUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public CommandResult execute(String robotId, String command) {
        return adapter.command(registry.get(robotId), command);
    }
}

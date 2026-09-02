package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import java.util.Map;

public class RelayPostWithBodyToRobotUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public RelayPostWithBodyToRobotUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public Map<String, Object> execute(String robotId, String path, Map<String, Object> body) {
        return adapter.post(registry.get(robotId), path, body);
    }
}

package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import java.util.Map;

public class RelayPostToRobotUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public RelayPostToRobotUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public Map<String, Object> execute(String robotId, String path) {
        return adapter.post(registry.get(robotId), path);
    }
}

package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import java.util.Map;

public class GetVoiceHealthUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetVoiceHealthUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public Map<String, Object> execute(String robotId) {
        return adapter.voiceHealth(registry.get(robotId));
    }
}

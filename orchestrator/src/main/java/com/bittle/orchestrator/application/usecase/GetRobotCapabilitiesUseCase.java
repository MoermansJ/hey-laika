package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import java.util.Map;

public class GetRobotCapabilitiesUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetRobotCapabilitiesUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public Map<String, Object> execute(String robotId) {
        return adapter.capabilities(fleet.get(robotId));
    }
}

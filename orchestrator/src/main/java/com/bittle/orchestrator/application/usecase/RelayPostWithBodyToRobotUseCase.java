package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import java.util.Map;

public class RelayPostWithBodyToRobotUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public RelayPostWithBodyToRobotUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public Map<String, Object> execute(String robotId, String path, Map<String, Object> body) {
        return adapter.post(fleet.get(robotId), path, body);
    }
}

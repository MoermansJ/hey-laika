package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.ActionFeed;

public class GetActionFeedUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    public GetActionFeedUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public ActionFeed execute(String robotId) {
        return adapter.actionFeed(fleet.get(robotId));
    }
}

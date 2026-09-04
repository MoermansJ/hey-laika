package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.ExecuteActionRequest;

public class ExecuteRobotActionUseCase {

    private final Fleet fleet;
    private final RobotAdapterPort adapter;
    private final BehaviorLoops loops;

    public ExecuteRobotActionUseCase(Fleet fleet, RobotAdapterPort adapter, BehaviorLoops loops) {
        this.fleet = fleet;
        this.adapter = adapter;
        this.loops = loops;
    }

    public ActionResult execute(String robotId, ExecuteActionRequest request) {
        var loop = loops.loop(robotId);
        if (loop.isRunning() || loop.remoteLease().isPresent()) {
            throw new BehaviorLoopRunningException();
        }
        return adapter.executeAction(fleet.get(robotId), request);
    }
}

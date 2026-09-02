package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.ExecuteActionRequest;

public class ExecuteRobotActionUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;
    private final BehaviorLoops loops;

    public ExecuteRobotActionUseCase(FleetRegistry registry, RobotAdapterPort adapter,
                                     BehaviorLoops loops) {
        this.registry = registry;
        this.adapter = adapter;
        this.loops = loops;
    }

    public ActionResult execute(String robotId, ExecuteActionRequest request) {
        if (loops.loop(robotId).isRunning()) {
            throw new BehaviorLoopRunningException();
        }
        return adapter.executeAction(registry.get(robotId), request);
    }
}

package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.AgentToolCatalog;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import com.bittle.orchestrator.domain.behavior.ToolDescriptor;
import com.bittle.orchestrator.domain.fleet.Fleet;
import java.util.List;

/** Tools the agent may call on a robot in its current operating mode (AGENT-14). */
public class GetAgentToolsUseCase {

    private final Fleet fleet;
    private final RobotModeRepositoryPort modes;

    public GetAgentToolsUseCase(Fleet fleet, RobotModeRepositoryPort modes) {
        this.fleet = fleet;
        this.modes = modes;
    }

    public List<ToolDescriptor> execute(String robotId) {
        fleet.get(robotId);
        RobotMode mode = modes.find(robotId).orElseGet(() -> RobotMode.initial(robotId));
        return AgentToolCatalog.toolsFor(mode.mode());
    }
}

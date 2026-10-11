package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetAgentToolsUseCase;
import com.bittle.orchestrator.application.usecase.GetLearnedPatternsUseCase;
import com.bittle.orchestrator.domain.behavior.ToolDescriptor;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Agent", description = "Agent tool composition: what Claude has learned works "
        + "for each goal")
@RequestMapping("/api/v1/agent")
public class AgentController {

    private final GetLearnedPatternsUseCase getLearnedPatterns;
    private final GetAgentToolsUseCase getAgentTools;

    public AgentController(GetLearnedPatternsUseCase getLearnedPatterns,
                           GetAgentToolsUseCase getAgentTools) {
        this.getLearnedPatterns = getLearnedPatterns;
        this.getAgentTools = getAgentTools;
    }

    @Operation(summary = "Tools the agent may call in the robot's current mode",
            description = "stationary: look_left, look_right, look_upward, tilt_head, bark, sit, "
                    + "stand. roaming: every tool, walking included. fruitfly and phone: none. "
                    + "404 robot_not_found for an unknown robot.")
    @GetMapping("/{robotId}/tools")
    public List<ToolDescriptor> agentTools(@PathVariable String robotId) {
        return getAgentTools.execute(robotId);
    }

    @Operation(summary = "Learned tool combinations for a goal",
            description = "Active patterns for the goal, highest success rate first (ties: more "
                    + "attempts first). Cached for 5 seconds. 404 robot_not_found for an unknown "
                    + "robot, 400 bad_request for a blank goal.")
    @GetMapping("/{robotId}/patterns")
    public List<LearnedPatternDTO> learnedPatterns(@PathVariable String robotId,
                                                   @RequestParam String goal) {
        return getLearnedPatterns.execute(robotId, goal).stream()
                .map(LearnedPatternDTO::from)
                .toList();
    }
}

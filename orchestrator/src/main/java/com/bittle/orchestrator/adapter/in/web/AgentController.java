package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetLearnedPatternsUseCase;
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

    public AgentController(GetLearnedPatternsUseCase getLearnedPatterns) {
        this.getLearnedPatterns = getLearnedPatterns;
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

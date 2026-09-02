package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.port.in.BehaviorUseCase;
import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import com.bittle.orchestrator.domain.behavior.BehaviorEvent;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.bittle.orchestrator.domain.robot.ActionResult;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Orchestrator-owned behavior/personality API. This replaces the deprecated
 * adapter-proxied personality/behavior/autonomous endpoints (see
 * docs/design/PERSONALITY_SYSTEM_DESIGN.md §2.3).
 */
@RestController
@RequestMapping("/api/robots/{robotId}/behavior")
public class BehaviorController {

    private final BehaviorUseCase behavior;

    public BehaviorController(BehaviorUseCase behavior) {
        this.behavior = behavior;
    }

    @GetMapping("/personality")
    public PersonalityState.Snapshot personality(@PathVariable String robotId) {
        return behavior.personality(robotId);
    }

    @GetMapping("/status")
    public BehaviorStatus status(@PathVariable String robotId) {
        return behavior.status(robotId);
    }

    @GetMapping("/history")
    public List<BehaviorDecision> history(@PathVariable String robotId,
                                          @RequestParam(defaultValue = "50") int limit) {
        return behavior.history(robotId, limit);
    }

    @PostMapping("/start")
    public BehaviorStatus start(@PathVariable String robotId) {
        return behavior.start(robotId);
    }

    @PostMapping("/stop")
    public BehaviorStatus stop(@PathVariable String robotId) {
        return behavior.stop(robotId);
    }

    @PostMapping("/event/{type}")
    public PersonalityState.Snapshot event(@PathVariable String robotId,
                                           @PathVariable String type) {
        return behavior.applyEvent(robotId, BehaviorEvent.fromName(type));
    }

    @PostMapping("/action/{action}")
    public ActionResult manualAction(@PathVariable String robotId,
                                     @PathVariable String action) {
        return behavior.submitManualAction(robotId, Action.fromActionId(action));
    }
}

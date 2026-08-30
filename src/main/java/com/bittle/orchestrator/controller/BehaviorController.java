package com.bittle.orchestrator.controller;

import com.bittle.orchestrator.behavior.Action;
import com.bittle.orchestrator.behavior.BehaviorDecision;
import com.bittle.orchestrator.behavior.BehaviorEvent;
import com.bittle.orchestrator.behavior.BehaviorService;
import com.bittle.orchestrator.behavior.PersonalityState;
import com.bittle.orchestrator.dto.Dtos.ActionResult;
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
 * docs/PERSONALITY_SYSTEM_DESIGN.md §2.3).
 */
@RestController
@RequestMapping("/api/robots/{robotId}/behavior")
public class BehaviorController {

    private final BehaviorService behaviorService;

    public BehaviorController(BehaviorService behaviorService) {
        this.behaviorService = behaviorService;
    }

    @GetMapping("/personality")
    public PersonalityState.Snapshot personality(@PathVariable String robotId) {
        return behaviorService.loop(robotId).personality();
    }

    @GetMapping("/status")
    public BehaviorStatus status(@PathVariable String robotId) {
        var loop = behaviorService.loop(robotId);
        return new BehaviorStatus(robotId, loop.isRunning(), loop.personality(),
                loop.lastDecision());
    }

    @GetMapping("/history")
    public List<BehaviorDecision> history(@PathVariable String robotId,
                                          @RequestParam(defaultValue = "50") int limit) {
        return behaviorService.loop(robotId).history(limit);
    }

    @PostMapping("/start")
    public BehaviorStatus start(@PathVariable String robotId) {
        behaviorService.loop(robotId).start();
        return status(robotId);
    }

    @PostMapping("/stop")
    public BehaviorStatus stop(@PathVariable String robotId) {
        behaviorService.loop(robotId).stop();
        return status(robotId);
    }

    @PostMapping("/event/{type}")
    public PersonalityState.Snapshot event(@PathVariable String robotId,
                                           @PathVariable String type) {
        return behaviorService.loop(robotId).applyEvent(BehaviorEvent.fromName(type));
    }

    @PostMapping("/action/{action}")
    public ActionResult manualAction(@PathVariable String robotId,
                                     @PathVariable String action) {
        return behaviorService.loop(robotId).submitManualAction(Action.fromActionId(action));
    }

    public record BehaviorStatus(String robotId, boolean running,
                                 PersonalityState.Snapshot personality,
                                 BehaviorDecision lastDecision) {
    }
}

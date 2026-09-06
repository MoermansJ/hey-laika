package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.ApplyBehaviorEventUseCase;
import com.bittle.orchestrator.application.usecase.GetBehaviorHistoryUseCase;
import com.bittle.orchestrator.application.usecase.GetBehaviorPersonalityUseCase;
import com.bittle.orchestrator.application.usecase.GetBehaviorStatusUseCase;
import com.bittle.orchestrator.application.usecase.StartBehaviorLoopUseCase;
import com.bittle.orchestrator.application.usecase.StopBehaviorLoopUseCase;
import com.bittle.orchestrator.application.usecase.SubmitManualActionUseCase;
import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.BehaviorDecision;
import com.bittle.orchestrator.domain.behavior.BehaviorEvent;
import com.bittle.orchestrator.domain.behavior.BehaviorStatus;
import com.bittle.orchestrator.domain.behavior.PersonalityState;
import com.bittle.orchestrator.domain.robot.ActionResult;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Behavior", description = "The orchestrator-owned brain: behavior loop and personality")
@RequestMapping("/api/robots/{robotId}/behavior")
public class BehaviorController {

    private final GetBehaviorPersonalityUseCase getPersonality;
    private final GetBehaviorStatusUseCase getStatus;
    private final GetBehaviorHistoryUseCase getHistory;
    private final StartBehaviorLoopUseCase startLoop;
    private final StopBehaviorLoopUseCase stopLoop;
    private final ApplyBehaviorEventUseCase applyEvent;
    private final SubmitManualActionUseCase submitManualAction;

    public BehaviorController(GetBehaviorPersonalityUseCase getPersonality,
                              GetBehaviorStatusUseCase getStatus,
                              GetBehaviorHistoryUseCase getHistory,
                              StartBehaviorLoopUseCase startLoop,
                              StopBehaviorLoopUseCase stopLoop,
                              ApplyBehaviorEventUseCase applyEvent,
                              SubmitManualActionUseCase submitManualAction) {
        this.getPersonality = getPersonality;
        this.getStatus = getStatus;
        this.getHistory = getHistory;
        this.startLoop = startLoop;
        this.stopLoop = stopLoop;
        this.applyEvent = applyEvent;
        this.submitManualAction = submitManualAction;
    }

    @Operation(summary = "Orchestrator personality snapshot",
            description = "Six dimensions and posture.")
    @GetMapping("/personality")
    public PersonalityState.Snapshot personality(@PathVariable String robotId) {
        return getPersonality.execute(robotId);
    }

    @Operation(summary = "Behavior loop status",
            description = "Loop running, owning instance, personality and last decision.")
    @GetMapping("/status")
    public BehaviorStatus status(@PathVariable String robotId) {
        return getStatus.execute(robotId);
    }

    @Operation(summary = "Recent decisions, newest first")
    @GetMapping("/history")
    public List<BehaviorDecision> history(@PathVariable String robotId,
                                          @RequestParam(defaultValue = "50") int limit) {
        return getHistory.execute(robotId, limit);
    }

    @Operation(summary = "Start the behavior loop",
            description = "409 behavior_loop_held_elsewhere while another instance holds its lease.")
    @PostMapping("/start")
    public BehaviorStatus start(@PathVariable String robotId) {
        return startLoop.execute(robotId);
    }

    @Operation(summary = "Stop the behavior loop")
    @PostMapping("/stop")
    public BehaviorStatus stop(@PathVariable String robotId) {
        return stopLoop.execute(robotId);
    }

    @Operation(summary = "Apply a personality event",
            description = "Unknown event names yield 400.")
    @PostMapping("/event/{type}")
    public PersonalityState.Snapshot event(@PathVariable String robotId,
                                           @PathVariable String type) {
        return applyEvent.execute(robotId, BehaviorEvent.fromName(type));
    }

    @Operation(summary = "Queue a manual action through the loop",
            description = "Executes immediately when the loop is stopped.")
    @PostMapping("/action/{action}")
    public ActionResult manualAction(@PathVariable String robotId,
                                     @PathVariable String action) {
        return submitManualAction.execute(robotId, Action.fromActionId(action));
    }
}

package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetRobotModeUseCase;
import com.bittle.orchestrator.application.usecase.SetRobotModeUseCase;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Mode", description = "Stationary Assistant, Roaming Assistant or Fruitfly: which "
        + "systems are allowed to move her, and why")
@RequestMapping("/api/robots/{robotId}/mode")
public class ModeController {

    private final GetRobotModeUseCase getMode;
    private final SetRobotModeUseCase setMode;

    public ModeController(GetRobotModeUseCase getMode, SetRobotModeUseCase setMode) {
        this.getMode = getMode;
        this.setMode = setMode;
    }

    @Operation(summary = "Current operating mode")
    @GetMapping
    public RobotMode mode(@PathVariable String robotId) {
        return getMode.execute(robotId);
    }

    @Operation(summary = "Switch operating mode",
            description = "stationary | roaming | fruitfly. The orchestrator's personality-tick "
                    + "behavior loop is always kept stopped (Stationary Assistant is a one-time "
                    + "sit, no autonomous movement — see PERSONALITY_MODES_BRIEF.md §2 and the "
                    + "2026-09-25 incident note in SetRobotModeUseCase), then relays the switch "
                    + "to the adapter, which owns conversation/navigation/fruitfly.")
    @PostMapping("/{mode}")
    public RobotMode set(@PathVariable String robotId, @PathVariable String mode,
                         @RequestParam(defaultValue = "gui") String via) {
        return setMode.execute(robotId, OperatingMode.fromWireId(mode), via);
    }
}

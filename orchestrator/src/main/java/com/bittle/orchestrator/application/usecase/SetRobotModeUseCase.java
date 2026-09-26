package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import com.bittle.orchestrator.domain.fleet.Fleet;
import java.time.Instant;
import java.util.Map;

public class SetRobotModeUseCase {

    private final Fleet fleet;
    private final RobotModeRepositoryPort modes;
    private final BehaviorLoops loops;
    private final RobotAdapterPort adapter;
    private final EventPublisherPort publisher;

    public SetRobotModeUseCase(Fleet fleet, RobotModeRepositoryPort modes, BehaviorLoops loops,
                               RobotAdapterPort adapter, EventPublisherPort publisher) {
        this.fleet = fleet;
        this.modes = modes;
        this.loops = loops;
        this.adapter = adapter;
        this.publisher = publisher;
    }

    public RobotMode execute(String robotId, OperatingMode mode, String changedBy) {
        var robot = fleet.get(robotId);
        // Stationary Assistant means no autonomous movement at all (2026-09-25
        // incident: RuleBasedDecisionEngine's idle/boredom branches picked
        // backflip/spin unattended) — the personality-tick loop never runs for
        // any mode until it's rebuilt to only ever propose in-place, non-motion
        // actions. Adapter-side mode.py still does a one-time idle_sit on
        // entering Stationary; nothing loops after that.
        loops.loop(robotId).stop();
        adapter.post(robot, "/mode", Map.of("mode", mode.wireId()));
        var record = new RobotMode(robotId, mode, Instant.now(), changedBy);
        modes.save(record);
        publisher.publish("/topic/robot/" + robotId + "/mode", record);
        return record;
    }
}

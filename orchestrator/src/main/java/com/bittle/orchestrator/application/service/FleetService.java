package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.in.FleetUseCase;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.FleetStats;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotInfo;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Fleet-wide queries; every adapter is polled in parallel and failures never propagate. */
public class FleetService implements FleetUseCase {

    private static final Logger log = LoggerFactory.getLogger(FleetService.class);

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public FleetService(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    @Override
    public List<RobotInfo> robots() {
        return registry.all().stream().map(Robot::info).toList();
    }

    @Override
    public Map<String, RobotStatus> fleetStatus() {
        return registry.all().parallelStream()
                .collect(Collectors.toMap(Robot::id, this::statusOrUnreachable));
    }

    @Override
    public FleetStats stats() {
        return FleetStats.of(fleetStatus().values());
    }

    @Override
    public Map<String, Boolean> startAllAutonomous() {
        return forAll(robot -> adapter.startAutonomous(robot).running());
    }

    @Override
    public Map<String, Boolean> stopAllAutonomous() {
        return forAll(robot -> !adapter.stopAutonomous(robot).running());
    }

    private RobotStatus statusOrUnreachable(Robot robot) {
        try {
            return adapter.status(robot);
        } catch (RuntimeException e) {
            log.warn("Robot {} unreachable: {}", robot.id(), e.getMessage());
            return RobotStatus.unreachable(robot.id());
        }
    }

    private Map<String, Boolean> forAll(Function<Robot, Boolean> action) {
        return registry.all().parallelStream()
                .collect(Collectors.toMap(Robot::id, robot -> {
                    try {
                        return action.apply(robot);
                    } catch (RuntimeException e) {
                        return false;
                    }
                }));
    }
}

package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.Map;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class GetFleetStatusUseCase {

    private static final Logger log = LoggerFactory.getLogger(GetFleetStatusUseCase.class);

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;

    public GetFleetStatusUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public Map<String, RobotStatus> execute() {
        return registry.all().parallelStream()
                .collect(Collectors.toMap(Robot::id, this::statusOrUnreachable));
    }

    private RobotStatus statusOrUnreachable(Robot robot) {
        try {
            return adapter.status(robot);
        } catch (RuntimeException e) {
            log.warn("Robot {} unreachable: {}", robot.id(), e.getMessage());
            return RobotStatus.unreachable(robot.id());
        }
    }
}

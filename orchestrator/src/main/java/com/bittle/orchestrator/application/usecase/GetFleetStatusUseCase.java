package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class GetFleetStatusUseCase {

    private static final Logger log = LoggerFactory.getLogger(GetFleetStatusUseCase.class);
    private static final long WARN_INTERVAL_MS = 60_000;

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;
    private final Map<String, Long> lastWarnAt = new ConcurrentHashMap<>();

    public GetFleetStatusUseCase(FleetRegistry registry, RobotAdapterPort adapter) {
        this.registry = registry;
        this.adapter = adapter;
    }

    public Map<String, RobotStatus> execute() {
        Map<String, RobotStatus> statuses = new LinkedHashMap<>();
        registry.all().forEach(robot -> statuses.put(robot.id(), statusOrUnreachable(robot)));
        return statuses;
    }

    private RobotStatus statusOrUnreachable(Robot robot) {
        try {
            var status = adapter.status(robot);
            lastWarnAt.remove(robot.id());
            return status;
        } catch (RuntimeException e) {
            warnThrottled(robot, e);
            return RobotStatus.unreachable(robot.id());
        }
    }

    private void warnThrottled(Robot robot, RuntimeException e) {
        long now = System.currentTimeMillis();
        var previous = lastWarnAt.get(robot.id());
        if (previous == null || now - previous >= WARN_INTERVAL_MS) {
            lastWarnAt.put(robot.id(), now);
            log.warn("Robot {} unreachable: {}", robot.id(), e.getMessage());
        } else {
            log.debug("Robot {} still unreachable: {}", robot.id(), e.getMessage());
        }
    }
}

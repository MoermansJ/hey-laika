package com.bittle.orchestrator.domain.fleet;

import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.Collection;

/** Fleet-wide counts derived from one status sweep. */
public record FleetStats(int totalRobots, long connectedRobots, long autonomousRobots,
                         long timestamp) {

    public static FleetStats of(Collection<RobotStatus> statuses) {
        long connected = statuses.stream().filter(RobotStatus::connected).count();
        long autonomous = statuses.stream()
                .filter(status -> Boolean.TRUE.equals(status.autonomous())).count();
        return new FleetStats(statuses.size(), connected, autonomous, System.currentTimeMillis());
    }
}

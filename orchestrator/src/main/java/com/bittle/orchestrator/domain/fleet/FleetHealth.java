package com.bittle.orchestrator.domain.fleet;

import java.time.Instant;
import java.util.Map;

public record FleetHealth(String status, String service, int fleetSize,
                          Map<String, RobotHealth> robots, Instant timestamp) {

    public static final String SERVICE = "bittle-orchestrator";

    public record RobotHealth(String name, boolean reachable, Boolean connected) {
    }

    public static FleetHealth of(Map<String, RobotHealth> robots, Instant now) {
        long reachable = robots.values().stream().filter(RobotHealth::reachable).count();
        String status;
        if (robots.isEmpty() || reachable == robots.size()) {
            status = "healthy";
        } else if (reachable == 0) {
            status = "down";
        } else {
            status = "degraded";
        }
        return new FleetHealth(status, SERVICE, robots.size(), robots, now);
    }
}

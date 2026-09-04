package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.FleetHealth;
import com.bittle.orchestrator.domain.fleet.FleetHealth.RobotHealth;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class GetFleetHealthUseCase {

    private static final long CACHE_MS = 3_000;

    private final Fleet fleet;
    private final RobotAdapterPort adapter;

    private volatile FleetHealth cached;
    private volatile long cachedAt;

    public GetFleetHealthUseCase(Fleet fleet, RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.adapter = adapter;
    }

    public FleetHealth execute() {
        long now = System.currentTimeMillis();
        var snapshot = cached;
        if (snapshot != null && now - cachedAt < CACHE_MS) {
            return snapshot;
        }
        synchronized (this) {
            if (cached != null && System.currentTimeMillis() - cachedAt < CACHE_MS) {
                return cached;
            }
            cached = probe();
            cachedAt = System.currentTimeMillis();
            return cached;
        }
    }

    private FleetHealth probe() {
        Map<String, RobotHealth> robots = new LinkedHashMap<>();
        for (Robot robot : fleet.all()) {
            robots.put(robot.id(), probe(robot));
        }
        return FleetHealth.of(robots, Instant.now());
    }

    private RobotHealth probe(Robot robot) {
        try {
            var status = adapter.status(robot);
            return new RobotHealth(robot.name(), true, status.connected());
        } catch (RuntimeException e) {
            return new RobotHealth(robot.name(), false, null);
        }
    }
}

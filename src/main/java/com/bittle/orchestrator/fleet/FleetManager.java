package com.bittle.orchestrator.fleet;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.dto.Dtos.FleetStats;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.exception.RobotNotFoundException;
import java.util.Collection;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/** In-memory registry of the live robot agents in the fleet. */
@Component
public class FleetManager {

    private final Map<String, RobotAgent> robots = new ConcurrentHashMap<>();

    public void register(RobotAgent agent) {
        robots.put(agent.id(), agent);
    }

    public void deregister(String robotId) {
        robots.remove(robotId);
    }

    public RobotAgent get(String robotId) {
        var agent = robots.get(robotId);
        if (agent == null) {
            throw new RobotNotFoundException(robotId);
        }
        return agent;
    }

    public Collection<RobotAgent> all() {
        return robots.values();
    }

    public Map<String, RobotStatus> fleetStatus() {
        return robots.values().parallelStream()
                .collect(Collectors.toMap(RobotAgent::id, RobotAgent::statusOrUnreachable));
    }

    public FleetStats stats() {
        var statuses = fleetStatus();
        long connected = statuses.values().stream().filter(RobotStatus::connected).count();
        long autonomous = statuses.values().stream()
                .filter(s -> Boolean.TRUE.equals(s.autonomous())).count();
        return new FleetStats(robots.size(), connected, autonomous, System.currentTimeMillis());
    }

    public Map<String, Boolean> forAll(Function<RobotAgent, Boolean> action) {
        return robots.values().parallelStream()
                .collect(Collectors.toMap(RobotAgent::id, agent -> {
                    try {
                        return action.apply(agent);
                    } catch (RuntimeException e) {
                        return false;
                    }
                }));
    }
}

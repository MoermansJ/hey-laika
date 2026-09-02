package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.util.Collection;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class FleetRegistry {

    private final Map<String, Robot> robots = new ConcurrentHashMap<>();

    public void register(Robot robot) {
        robots.put(robot.id(), robot);
    }

    public void deregister(String robotId) {
        robots.remove(robotId);
    }

    public Robot get(String robotId) {
        var robot = robots.get(robotId);
        if (robot == null) {
            throw new RobotNotFoundException(robotId);
        }
        return robot;
    }

    public Collection<Robot> all() {
        return robots.values();
    }
}

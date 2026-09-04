package com.bittle.orchestrator.domain.fleet;

import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class Fleet {

    private final Map<String, Robot> robots;

    public Fleet(List<Robot> robots) {
        Map<String, Robot> byId = new LinkedHashMap<>();
        for (var robot : robots) {
            if (byId.putIfAbsent(robot.id(), robot) != null) {
                throw new IllegalArgumentException("Duplicate robot id: " + robot.id());
            }
        }
        this.robots = Collections.unmodifiableMap(byId);
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

    public boolean isEmpty() {
        return robots.isEmpty();
    }
}

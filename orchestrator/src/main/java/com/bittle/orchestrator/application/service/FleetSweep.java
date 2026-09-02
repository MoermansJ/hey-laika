package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;

public class FleetSweep {

    private final FleetRegistry registry;

    public FleetSweep(FleetRegistry registry) {
        this.registry = registry;
    }

    public Map<String, Boolean> forAll(Function<Robot, Boolean> action) {
        Map<String, Boolean> results = new LinkedHashMap<>();
        for (Robot robot : registry.all()) {
            results.put(robot.id(), attempt(action, robot));
        }
        return results;
    }

    private static Boolean attempt(Function<Robot, Boolean> action, Robot robot) {
        try {
            return action.apply(robot);
        } catch (RuntimeException e) {
            return false;
        }
    }
}

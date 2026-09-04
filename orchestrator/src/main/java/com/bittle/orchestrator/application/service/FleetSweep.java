package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;

public class FleetSweep {

    private final Fleet fleet;

    public FleetSweep(Fleet fleet) {
        this.fleet = fleet;
    }

    public Map<String, Boolean> forAll(Function<Robot, Boolean> action) {
        Map<String, Boolean> results = new LinkedHashMap<>();
        for (Robot robot : fleet.all()) {
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

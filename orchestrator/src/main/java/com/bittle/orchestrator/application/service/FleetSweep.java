package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class FleetSweep {

    private final FleetRegistry registry;

    public FleetSweep(FleetRegistry registry) {
        this.registry = registry;
    }

    public Map<String, Boolean> forAll(Function<Robot, Boolean> action) {
        return registry.all().parallelStream()
                .collect(Collectors.toMap(Robot::id, robot -> {
                    try {
                        return action.apply(robot);
                    } catch (RuntimeException e) {
                        return false;
                    }
                }));
    }
}

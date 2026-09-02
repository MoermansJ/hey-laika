package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import org.junit.jupiter.api.Test;

class FleetRegistryTest {

    private final FleetRegistry registry = new FleetRegistry();

    @Test
    void givenEmptyRegistry_whenUnknownRobotRequested_thenRobotNotFoundIsThrown() {
        assertThatThrownBy(() -> registry.get("ghost"))
                .isInstanceOf(RobotNotFoundException.class);
    }

    @Test
    void givenRegisteredRobot_whenRequestedById_thenTheSameRobotIsReturned() {
        var robot = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://localhost:15001");

        registry.register(robot);

        assertThat(registry.get("bittle-1")).isSameAs(robot);
        assertThat(registry.all()).containsExactly(robot);
    }

    @Test
    void givenRegisteredRobot_whenDeregistered_thenItIsGone() {
        registry.register(new Robot("bittle-1", "Laika", "bittle_x_v2", "http://localhost:15001"));

        registry.deregister("bittle-1");

        assertThat(registry.all()).isEmpty();
    }
}

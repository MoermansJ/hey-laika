package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.AutonomousState;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import org.junit.jupiter.api.Test;

class FleetServiceTest {

    private static final Robot UP = new Robot("up", "Up", "mock", "http://up");
    private static final Robot DOWN = new Robot("down", "Down", "mock", "http://down");

    private final FleetRegistry registry = new FleetRegistry();
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final FleetService service = new FleetService(registry, adapter);

    @Test
    void givenRegisteredRobots_whenListed_thenEachIsReportedActive() {
        registry.register(UP);

        var robots = service.robots();

        assertThat(robots).singleElement().satisfies(info -> {
            assertThat(info.robotId()).isEqualTo("up");
            assertThat(info.active()).isTrue();
        });
    }

    @Test
    void givenOneConnectedAndOneUnreachableRobot_whenStatsRequested_thenCountsReflectBoth() {
        registry.register(UP);
        registry.register(DOWN);
        when(adapter.status(UP)).thenReturn(new RobotStatus("up", true, "mock", null, 3, true,
                "happy", 90.0, "strong", 60L, 1000.0));
        when(adapter.status(DOWN)).thenThrow(new AdapterUnavailableException("http://down", null));

        var stats = service.stats();

        assertThat(stats.totalRobots()).isEqualTo(2);
        assertThat(stats.connectedRobots()).isEqualTo(1);
        assertThat(stats.autonomousRobots()).isEqualTo(1);
    }

    @Test
    void givenUnreachableRobot_whenFleetStatusRequested_thenItIsReportedUnreachable() {
        registry.register(DOWN);
        when(adapter.status(DOWN)).thenThrow(new AdapterUnavailableException("http://down", null));

        var statuses = service.fleetStatus();

        assertThat(statuses).containsEntry("down", RobotStatus.unreachable("down"));
    }

    @Test
    void givenFailingAdapter_whenStartingAllAutonomous_thenTheFailureIsReportedAsFalse() {
        registry.register(DOWN);
        when(adapter.startAutonomous(any())).thenThrow(new IllegalStateException("boom"));

        var result = service.startAllAutonomous();

        assertThat(result).containsEntry("down", false);
    }

    @Test
    void givenRunningAdapter_whenStoppingAllAutonomous_thenStoppedRobotsReportTrue() {
        registry.register(UP);
        when(adapter.stopAutonomous(UP)).thenReturn(new AutonomousState("up", false, true, null));

        var result = service.stopAllAutonomous();

        assertThat(result).containsEntry("up", true);
    }
}

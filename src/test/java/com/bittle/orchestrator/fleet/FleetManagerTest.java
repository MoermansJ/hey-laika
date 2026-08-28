package com.bittle.orchestrator.fleet;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.exception.RobotNotFoundException;
import org.junit.jupiter.api.Test;

class FleetManagerTest {

    @Test
    void getUnknownRobotThrows() {
        var fleet = new FleetManager();
        assertThatThrownBy(() -> fleet.get("ghost"))
                .isInstanceOf(RobotNotFoundException.class);
    }

    @Test
    void registeredRobotIsRetrievable() {
        var fleet = new FleetManager();
        var agent = mock(RobotAgent.class);
        when(agent.id()).thenReturn("bittle-1");
        fleet.register(agent);

        assertThat(fleet.get("bittle-1")).isSameAs(agent);
        assertThat(fleet.all()).hasSize(1);
    }

    @Test
    void statsCountConnectedAndAutonomousRobots() {
        var fleet = new FleetManager();
        var up = mock(RobotAgent.class);
        when(up.id()).thenReturn("up");
        when(up.statusOrUnreachable())
                .thenReturn(new RobotStatus("up", true, "mock", null, 3, true, "happy"));
        var down = mock(RobotAgent.class);
        when(down.id()).thenReturn("down");
        when(down.statusOrUnreachable()).thenReturn(RobotStatus.unreachable("down"));

        fleet.register(up);
        fleet.register(down);

        var stats = fleet.stats();
        assertThat(stats.totalRobots()).isEqualTo(2);
        assertThat(stats.connectedRobots()).isEqualTo(1);
        assertThat(stats.autonomousRobots()).isEqualTo(1);
    }

    @Test
    void forAllTurnsAgentFailuresIntoFalse() {
        var fleet = new FleetManager();
        var flaky = mock(RobotAgent.class);
        when(flaky.id()).thenReturn("flaky");
        fleet.register(flaky);

        var result = fleet.forAll(agent -> { throw new IllegalStateException("boom"); });
        assertThat(result).containsEntry("flaky", false);
    }
}

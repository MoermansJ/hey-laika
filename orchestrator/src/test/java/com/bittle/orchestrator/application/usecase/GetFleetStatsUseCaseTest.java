package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.Map;
import org.junit.jupiter.api.Test;

class GetFleetStatsUseCaseTest {

    private final GetFleetStatusUseCase fleetStatus = mock(GetFleetStatusUseCase.class);
    private final GetFleetStatsUseCase useCase = new GetFleetStatsUseCase(fleetStatus);

    @Test
    void givenOneConnectedAutonomousAndOneUnreachableRobot_whenExecuted_thenCountsReflectBoth() {
        when(fleetStatus.execute()).thenReturn(Map.of(
                "up", new RobotStatus("up", true, "mock", null, 3, true, "happy",
                        90.0, "strong", 60L, 1000.0),
                "down", RobotStatus.unreachable("down")));

        var stats = useCase.execute();

        assertThat(stats.totalRobots()).isEqualTo(2);
        assertThat(stats.connectedRobots()).isEqualTo(1);
        assertThat(stats.autonomousRobots()).isEqualTo(1);
    }
}

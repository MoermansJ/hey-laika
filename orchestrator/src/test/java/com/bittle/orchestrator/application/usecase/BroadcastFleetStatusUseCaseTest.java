package com.bittle.orchestrator.application.usecase;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.Map;
import org.junit.jupiter.api.Test;

class BroadcastFleetStatusUseCaseTest {

    private static final Robot ONE = new Robot("bittle-1", "One", "mock", "http://one");
    private static final Robot TWO = new Robot("bittle-2", "Two", "mock", "http://two");

    private final FleetRegistry registry = new FleetRegistry();
    private final GetFleetStatusUseCase fleetStatus = mock(GetFleetStatusUseCase.class);
    private final EventPublisherPort publisher = mock(EventPublisherPort.class);
    private final BroadcastFleetStatusUseCase useCase =
            new BroadcastFleetStatusUseCase(registry, fleetStatus, publisher);

    @Test
    void givenEmptyFleet_whenExecuted_thenNothingIsPublishedAndNoSweepRuns() {
        useCase.execute();

        verifyNoInteractions(publisher, fleetStatus);
    }

    @Test
    void givenTwoRobots_whenExecuted_thenOneSweepFeedsFleetRobotAndStatsTopics() {
        registry.register(ONE);
        registry.register(TWO);
        when(fleetStatus.execute()).thenReturn(Map.of(
                "bittle-1", new RobotStatus("bittle-1", true, "mock", null, 0, true, "happy",
                        80.0, "strong", 10L, 1000.0),
                "bittle-2", RobotStatus.unreachable("bittle-2")));

        useCase.execute();

        verify(fleetStatus).execute();
        verify(publisher).publish(eq("/topic/fleet/status"), any());
        verify(publisher).publish(eq("/topic/robot/bittle-1/status"), any());
        verify(publisher).publish(eq("/topic/robot/bittle-2/status"), any());
        verify(publisher).publish(eq("/topic/fleet/stats"), any());
    }
}

package com.bittle.orchestrator.application.service;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.ActivityLog;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.List;
import org.junit.jupiter.api.Test;

class FleetBroadcastServiceTest {

    private static final Robot ONE = new Robot("bittle-1", "One", "mock", "http://one");
    private static final Robot TWO = new Robot("bittle-2", "Two", "mock", "http://two");

    private final FleetRegistry registry = new FleetRegistry();
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final EventPublisherPort publisher = mock(EventPublisherPort.class);
    private final FleetBroadcastService service = new FleetBroadcastService(registry,
            new FleetService(registry, adapter), adapter, publisher);

    @Test
    void givenEmptyFleet_whenStatusSweepRuns_thenNothingIsPublished() {
        service.broadcastStatus();

        verifyNoInteractions(publisher);
    }

    @Test
    void givenTwoRobots_whenStatusSweepRuns_thenFleetRobotAndStatsTopicsAreFed() {
        registry.register(ONE);
        registry.register(TWO);
        when(adapter.status(ONE)).thenReturn(new RobotStatus("bittle-1", true, "mock", null, 0,
                true, "happy", 80.0, "strong", 10L, 1000.0));
        when(adapter.status(TWO)).thenThrow(new AdapterUnavailableException("http://two", null));

        service.broadcastStatus();

        verify(publisher).publish(eq("/topic/fleet/status"), any());
        verify(publisher).publish(eq("/topic/robot/bittle-1/status"), any());
        verify(publisher).publish(eq("/topic/robot/bittle-2/status"), any());
        verify(publisher).publish(eq("/topic/fleet/stats"), any());
    }

    @Test
    void givenOneUnreachableRobot_whenActivitySweepRuns_thenTheOtherIsStillPublished() {
        registry.register(ONE);
        registry.register(TWO);
        when(adapter.activity(ONE)).thenReturn(new ActivityLog("bittle-1", List.of()));
        when(adapter.activity(TWO)).thenThrow(new AdapterUnavailableException("http://two", null));

        service.broadcastActivity();

        verify(publisher).publish(eq("/topic/robot/bittle-1/activity"), any());
    }
}

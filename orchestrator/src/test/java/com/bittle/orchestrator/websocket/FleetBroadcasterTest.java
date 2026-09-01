package com.bittle.orchestrator.websocket;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.fleet.FleetManager;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

class FleetBroadcasterTest {

    private final SimpMessagingTemplate messaging = mock(SimpMessagingTemplate.class);
    private final FleetManager fleet = new FleetManager();
    private final FleetBroadcaster broadcaster = new FleetBroadcaster(fleet, messaging);

    private RobotAgent agent(String id, RobotStatus status) {
        var agent = mock(RobotAgent.class);
        when(agent.id()).thenReturn(id);
        when(agent.statusOrUnreachable()).thenReturn(status);
        return agent;
    }

    @Test
    void nothingIsBroadcastWithoutClients() {
        fleet.register(agent("bittle-1",
                new RobotStatus("bittle-1", true, "mock", null, 0, false, "happy",
                        80.0, "strong", 10L, 1000.0)));

        broadcaster.broadcastStatus();
        broadcaster.broadcastPersonalityAndDisplay();
        broadcaster.broadcastActivity();

        verifyNoInteractions(messaging);
    }

    @Test
    void statusSweepFeedsFleetRobotAndStatsTopics() {
        fleet.register(agent("bittle-1",
                new RobotStatus("bittle-1", true, "mock", null, 0, true, "happy",
                        80.0, "strong", 10L, 1000.0)));
        fleet.register(agent("bittle-2", RobotStatus.unreachable("bittle-2")));
        broadcaster.onSessionConnect(mock(SessionConnectEvent.class));

        broadcaster.broadcastStatus();

        verify(messaging).convertAndSend(eq("/topic/fleet/status"), any(Object.class));
        verify(messaging).convertAndSend(eq("/topic/robot/bittle-1/status"), any(Object.class));
        verify(messaging).convertAndSend(eq("/topic/robot/bittle-2/status"), any(Object.class));
        verify(messaging).convertAndSend(eq("/topic/fleet/stats"), any(Object.class));
    }

    @Test
    void disconnectingLastClientStopsBroadcasts() {
        broadcaster.onSessionConnect(mock(SessionConnectEvent.class));
        broadcaster.onSessionDisconnect(mock(SessionDisconnectEvent.class));
        // An unmatched disconnect must not push the count below zero.
        broadcaster.onSessionDisconnect(mock(SessionDisconnectEvent.class));

        fleet.register(agent("bittle-1", RobotStatus.unreachable("bittle-1")));
        broadcaster.broadcastStatus();

        verifyNoInteractions(messaging);
    }
}

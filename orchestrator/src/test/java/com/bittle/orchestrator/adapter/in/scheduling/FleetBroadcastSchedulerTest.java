package com.bittle.orchestrator.adapter.in.scheduling;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import com.bittle.orchestrator.application.port.in.FleetBroadcastUseCase;
import org.junit.jupiter.api.Test;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

class FleetBroadcastSchedulerTest {

    private final FleetBroadcastUseCase broadcast = mock(FleetBroadcastUseCase.class);
    private final FleetBroadcastScheduler scheduler = new FleetBroadcastScheduler(broadcast);

    @Test
    void givenNoConnectedClients_whenAnySweepFires_thenNothingIsBroadcast() {
        scheduler.broadcastStatus();
        scheduler.broadcastPersonalityAndDisplay();
        scheduler.broadcastActivity();

        verifyNoInteractions(broadcast);
    }

    @Test
    void givenConnectedClient_whenSweepsFire_thenEachBroadcastRuns() {
        scheduler.onSessionConnect(mock(SessionConnectEvent.class));

        scheduler.broadcastStatus();
        scheduler.broadcastPersonalityAndDisplay();
        scheduler.broadcastActivity();

        verify(broadcast).broadcastStatus();
        verify(broadcast).broadcastPersonalityAndDisplay();
        verify(broadcast).broadcastActivity();
    }

    @Test
    void givenLastClientDisconnected_whenStatusSweepFires_thenNothingIsBroadcast() {
        scheduler.onSessionConnect(mock(SessionConnectEvent.class));
        scheduler.onSessionDisconnect(mock(SessionDisconnectEvent.class));
        // An unmatched disconnect must not push the count below zero.
        scheduler.onSessionDisconnect(mock(SessionDisconnectEvent.class));

        scheduler.broadcastStatus();

        assertThat(scheduler.connectedClients()).isZero();
        verifyNoInteractions(broadcast);
    }
}

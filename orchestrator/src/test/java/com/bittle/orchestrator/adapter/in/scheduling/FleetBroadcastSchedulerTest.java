package com.bittle.orchestrator.adapter.in.scheduling;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import com.bittle.orchestrator.application.usecase.BroadcastActivityUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastFleetStatusUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastPersonalityAndDisplayUseCase;
import org.junit.jupiter.api.Test;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

class FleetBroadcastSchedulerTest {

    private final BroadcastFleetStatusUseCase broadcastStatus = mock(BroadcastFleetStatusUseCase.class);
    private final BroadcastPersonalityAndDisplayUseCase broadcastPersonalityAndDisplay =
            mock(BroadcastPersonalityAndDisplayUseCase.class);
    private final BroadcastActivityUseCase broadcastActivity = mock(BroadcastActivityUseCase.class);
    private final FleetBroadcastScheduler scheduler = new FleetBroadcastScheduler(
            broadcastStatus, broadcastPersonalityAndDisplay, broadcastActivity);

    @Test
    void givenNoConnectedClients_whenAnySweepFires_thenNoUseCaseRuns() {
        scheduler.broadcastStatus();
        scheduler.broadcastPersonalityAndDisplay();
        scheduler.broadcastActivity();

        verifyNoInteractions(broadcastStatus, broadcastPersonalityAndDisplay, broadcastActivity);
    }

    @Test
    void givenConnectedClient_whenSweepsFire_thenEachUseCaseRuns() {
        scheduler.onSessionConnect(mock(SessionConnectEvent.class));

        scheduler.broadcastStatus();
        scheduler.broadcastPersonalityAndDisplay();
        scheduler.broadcastActivity();

        verify(broadcastStatus).execute();
        verify(broadcastPersonalityAndDisplay).execute();
        verify(broadcastActivity).execute();
    }

    @Test
    void givenMoreDisconnectsThanConnects_whenStatusSweepFires_thenCountStaysAtZeroAndNothingRuns() {
        scheduler.onSessionConnect(mock(SessionConnectEvent.class));
        scheduler.onSessionDisconnect(mock(SessionDisconnectEvent.class));
        scheduler.onSessionDisconnect(mock(SessionDisconnectEvent.class));

        scheduler.broadcastStatus();

        assertThat(scheduler.connectedClients()).isZero();
        verifyNoInteractions(broadcastStatus);
    }
}

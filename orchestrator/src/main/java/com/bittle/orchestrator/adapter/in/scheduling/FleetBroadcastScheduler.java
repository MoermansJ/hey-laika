package com.bittle.orchestrator.adapter.in.scheduling;

import com.bittle.orchestrator.application.usecase.BroadcastActivityUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastFleetStatusUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastPersonalityAndDisplayUseCase;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class FleetBroadcastScheduler {

    private final BroadcastFleetStatusUseCase broadcastStatus;
    private final BroadcastPersonalityAndDisplayUseCase broadcastPersonalityAndDisplay;
    private final BroadcastActivityUseCase broadcastActivity;
    private final AtomicInteger clients = new AtomicInteger();

    public FleetBroadcastScheduler(BroadcastFleetStatusUseCase broadcastStatus,
                                   BroadcastPersonalityAndDisplayUseCase broadcastPersonalityAndDisplay,
                                   BroadcastActivityUseCase broadcastActivity) {
        this.broadcastStatus = broadcastStatus;
        this.broadcastPersonalityAndDisplay = broadcastPersonalityAndDisplay;
        this.broadcastActivity = broadcastActivity;
    }

    @EventListener
    public void onSessionConnect(SessionConnectEvent event) {
        clients.incrementAndGet();
    }

    @EventListener
    public void onSessionDisconnect(SessionDisconnectEvent event) {
        clients.updateAndGet(n -> Math.max(0, n - 1));
    }

    int connectedClients() {
        return clients.get();
    }

    @Scheduled(fixedRate = 4000)
    public void broadcastStatus() {
        if (hasClients()) {
            broadcastStatus.execute();
        }
    }

    @Scheduled(fixedRate = 3000)
    public void broadcastPersonalityAndDisplay() {
        if (hasClients()) {
            broadcastPersonalityAndDisplay.execute();
        }
    }

    @Scheduled(fixedRate = 5000)
    public void broadcastActivity() {
        if (hasClients()) {
            broadcastActivity.execute();
        }
    }

    private boolean hasClients() {
        return clients.get() > 0;
    }
}

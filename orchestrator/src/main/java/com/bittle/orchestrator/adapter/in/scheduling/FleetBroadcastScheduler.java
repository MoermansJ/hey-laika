package com.bittle.orchestrator.adapter.in.scheduling;

import com.bittle.orchestrator.application.port.in.FleetBroadcastUseCase;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

/**
 * Drives the fleet broadcasts on a fixed cadence. Broadcasts are skipped
 * while no WebSocket client is connected so the Python adapters are not
 * polled for nobody.
 */
@Component
public class FleetBroadcastScheduler {

    private final FleetBroadcastUseCase broadcast;
    private final AtomicInteger clients = new AtomicInteger();

    public FleetBroadcastScheduler(FleetBroadcastUseCase broadcast) {
        this.broadcast = broadcast;
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

    /** 4s (was 2s): halved per owner request — with the adapter's 40s
     *  telemetry TTL this keeps dog-facing traffic minimal. */
    @Scheduled(fixedRate = 4000)
    public void broadcastStatus() {
        if (hasClients()) {
            broadcast.broadcastStatus();
        }
    }

    @Scheduled(fixedRate = 3000)
    public void broadcastPersonalityAndDisplay() {
        if (hasClients()) {
            broadcast.broadcastPersonalityAndDisplay();
        }
    }

    @Scheduled(fixedRate = 5000)
    public void broadcastActivity() {
        if (hasClients()) {
            broadcast.broadcastActivity();
        }
    }

    private boolean hasClients() {
        return clients.get() > 0;
    }
}

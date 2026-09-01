package com.bittle.orchestrator.websocket;

import com.bittle.orchestrator.dto.Dtos.FleetStats;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.fleet.FleetManager;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

/**
 * Pushes fleet and robot state to STOMP topics on a fixed cadence. Broadcasts
 * are skipped while no WebSocket client is connected so the Python adapters
 * are not polled for nobody.
 */
@Component
public class FleetBroadcaster {

    private static final Logger log = LoggerFactory.getLogger(FleetBroadcaster.class);

    private final FleetManager fleetManager;
    private final SimpMessagingTemplate messaging;
    private final AtomicInteger clients = new AtomicInteger();

    public FleetBroadcaster(FleetManager fleetManager, SimpMessagingTemplate messaging) {
        this.fleetManager = fleetManager;
        this.messaging = messaging;
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

    /** One adapter sweep feeds fleet status, per-robot status, and stats.
     *  4s (was 2s): halved per owner request — with the adapter's 40s
     *  telemetry TTL this keeps dog-facing traffic minimal. */
    @Scheduled(fixedRate = 4000)
    public void broadcastStatus() {
        if (clients.get() == 0 || fleetManager.all().isEmpty()) {
            return;
        }
        var statuses = fleetManager.fleetStatus();
        messaging.convertAndSend("/topic/fleet/status", statuses);
        statuses.forEach((id, status) ->
                messaging.convertAndSend("/topic/robot/" + id + "/status", status));

        long connected = statuses.values().stream().filter(RobotStatus::connected).count();
        long autonomous = statuses.values().stream()
                .filter(s -> Boolean.TRUE.equals(s.autonomous())).count();
        messaging.convertAndSend("/topic/fleet/stats",
                new FleetStats(statuses.size(), connected, autonomous,
                        System.currentTimeMillis()));
    }

    @Scheduled(fixedRate = 3000)
    public void broadcastPersonalityAndDisplay() {
        if (clients.get() == 0) {
            return;
        }
        for (var agent : fleetManager.all()) {
            try {
                messaging.convertAndSend("/topic/robot/" + agent.id() + "/personality",
                        agent.personality());
                messaging.convertAndSend("/topic/robot/" + agent.id() + "/display",
                        agent.display());
            } catch (RuntimeException e) {
                log.debug("Skipping personality/display broadcast for {}: {}",
                        agent.id(), e.getMessage());
            }
        }
    }

    @Scheduled(fixedRate = 5000)
    public void broadcastActivity() {
        if (clients.get() == 0) {
            return;
        }
        for (var agent : fleetManager.all()) {
            try {
                messaging.convertAndSend("/topic/robot/" + agent.id() + "/activity",
                        agent.activity());
            } catch (RuntimeException e) {
                log.debug("Skipping activity broadcast for {}: {}", agent.id(), e.getMessage());
            }
        }
    }
}

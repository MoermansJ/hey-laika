package com.bittle.orchestrator.adapter.in.scheduling;

import com.bittle.orchestrator.application.usecase.BroadcastActionFeedUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastActivityUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastFleetStatusUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastFruitflyUseCase;
import com.bittle.orchestrator.application.usecase.BroadcastPersonalityAndDisplayUseCase;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.AbstractSubProtocolEvent;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class FleetBroadcastScheduler {

    private final BroadcastFleetStatusUseCase broadcastStatus;
    private final BroadcastPersonalityAndDisplayUseCase broadcastPersonalityAndDisplay;
    private final BroadcastActivityUseCase broadcastActivity;
    private final BroadcastFruitflyUseCase broadcastFruitfly;
    private final BroadcastActionFeedUseCase broadcastActionFeed;
    private final Set<String> sessions = ConcurrentHashMap.newKeySet();

    public FleetBroadcastScheduler(BroadcastFleetStatusUseCase broadcastStatus,
                                   BroadcastPersonalityAndDisplayUseCase broadcastPersonalityAndDisplay,
                                   BroadcastActivityUseCase broadcastActivity,
                                   BroadcastFruitflyUseCase broadcastFruitfly,
                                   BroadcastActionFeedUseCase broadcastActionFeed) {
        this.broadcastStatus = broadcastStatus;
        this.broadcastPersonalityAndDisplay = broadcastPersonalityAndDisplay;
        this.broadcastActivity = broadcastActivity;
        this.broadcastFruitfly = broadcastFruitfly;
        this.broadcastActionFeed = broadcastActionFeed;
    }

    @EventListener
    public void onSessionConnect(SessionConnectEvent event) {
        var id = sessionId(event);
        sessions.add(id != null ? id : "anonymous-" + System.identityHashCode(event));
    }

    @EventListener
    public void onSessionDisconnect(SessionDisconnectEvent event) {
        var id = event.getSessionId() != null ? event.getSessionId() : sessionId(event);
        if (id != null) {
            sessions.remove(id);
            return;
        }
        sessions.stream().findFirst().ifPresent(sessions::remove);
    }

    int connectedClients() {
        return sessions.size();
    }

    @Scheduled(fixedRate = 4000)
    public void broadcastStatus() {
        if (hasClients()) {
            broadcastStatus.execute();
        }
    }

    @Scheduled(fixedRate = 10000)
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

    @Scheduled(fixedRate = 2000)
    public void broadcastFruitfly() {
        if (hasClients()) {
            broadcastFruitfly.execute();
        }
    }

    // Actions land about once a second while a mode is driving, so this
    // sweeps faster than the others — at 4s the console would miss most of
    // them between updates.
    @Scheduled(fixedRate = 1000)
    public void broadcastActionFeed() {
        if (hasClients()) {
            broadcastActionFeed.execute();
        }
    }

    private boolean hasClients() {
        return !sessions.isEmpty();
    }

    private static String sessionId(AbstractSubProtocolEvent event) {
        var message = event.getMessage();
        if (message == null) {
            return null;
        }
        return SimpMessageHeaderAccessor.getSessionId(message.getHeaders());
    }
}

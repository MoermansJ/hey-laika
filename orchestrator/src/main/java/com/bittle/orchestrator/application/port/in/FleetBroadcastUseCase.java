package com.bittle.orchestrator.application.port.in;

/** Pushes fleet and robot state to the dashboard topics. */
public interface FleetBroadcastUseCase {

    /** One adapter sweep feeds fleet status, per-robot status, and stats. */
    void broadcastStatus();

    void broadcastPersonalityAndDisplay();

    void broadcastActivity();
}

package com.bittle.orchestrator.domain.behavior;

/**
 * External events that shift personality state. Hardware-sourced (back touch
 * sensor, voice module, IMU) and API-sourced (dashboard) events share the same
 * handling in {@link PersonalityStateManager}.
 */
public enum BehaviorEvent {
    OWNER_PETTED,
    OWNER_CALLED_OUT,
    OWNER_PLAYED,
    PICKED_UP,
    FELL_OVER,
    LOW_BATTERY;

    public static BehaviorEvent fromName(String name) {
        return valueOf(name.trim().toUpperCase().replace('-', '_'));
    }

    public boolean ownerInteraction() {
        return this == OWNER_PETTED || this == OWNER_CALLED_OUT || this == OWNER_PLAYED;
    }
}

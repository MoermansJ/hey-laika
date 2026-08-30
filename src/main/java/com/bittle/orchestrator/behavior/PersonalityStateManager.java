package com.bittle.orchestrator.behavior;

import java.time.Duration;
import java.time.Instant;
import org.springframework.stereotype.Component;

/**
 * Applies all personality mutations: action impacts, passive per-cycle drift
 * and external events. Energy is changed only by actions — there is no
 * separate passive energy decay competing with recovery actions.
 */
@Component
public class PersonalityStateManager {

    static final Duration LONELINESS_THRESHOLD = Duration.ofSeconds(30);
    private static final double SLEEP_BOREDOM_CAP = 0.3;

    /** Applies the outcome of an executed action. Failed actions change nothing but the log. */
    public void onActionCompleted(PersonalityState state, Action action, boolean success,
                                  Instant now) {
        state.recordAction(action, now);
        if (!success) {
            return;
        }
        state.apply(action.impact());
        if (action == Action.SLEEP) {
            state.capBoredom(SLEEP_BOREDOM_CAP);
        }
        state.setPosture(action.postureAfter(state.posture()));
    }

    /** Per-cycle drift: loneliness, boredom growth, contentment toward neutral. */
    public void applyPassiveDrift(PersonalityState state, Instant now) {
        boolean lonely = state.lastInteractionAt() == null
                || Duration.between(state.lastInteractionAt(), now)
                        .compareTo(LONELINESS_THRESHOLD) > 0;
        boolean sleeping = state.posture() == Posture.SLEEPING;
        double boredomGrowth = sleeping ? 0.0 : 0.01;
        // Energy recovers while asleep so the robot eventually wakes on its own.
        // Curiosity builds slowly while awake and is satisfied by exploring.
        state.apply(new PersonalityDelta(sleeping ? 0.05 : 0,
                lonely ? -0.005 : 0,
                boredomGrowth,
                sleeping ? 0 : 0.005,
                lonely ? 0.01 : 0,
                0));
        state.driftContentmentTowardNeutral(0.02);
    }

    /** Applies an external owner/sensor event. */
    public void applyEvent(PersonalityState state, BehaviorEvent event, Instant now) {
        switch (event) {
            case OWNER_PETTED -> state.apply(new PersonalityDelta(0, 0.15, 0, 0, -0.10, 0));
            case OWNER_CALLED_OUT -> state.apply(new PersonalityDelta(0, 0, 0, 0.10, -0.20, 0));
            case OWNER_PLAYED -> state.apply(new PersonalityDelta(-0.15, 0.20, -0.30, 0, 0, 0));
            case PICKED_UP, FELL_OVER -> {
                state.apply(new PersonalityDelta(0, 0, 0, 0.10, 0, -0.10));
                // IMU says we are no longer in the posture we assumed.
                state.setPosture(Posture.LYING);
            }
            case LOW_BATTERY -> state.apply(new PersonalityDelta(-0.30, 0, 0, 0, 0, 0));
        }
        if (event.ownerInteraction()) {
            state.recordInteraction(now);
        }
    }
}

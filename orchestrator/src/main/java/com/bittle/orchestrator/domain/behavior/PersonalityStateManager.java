package com.bittle.orchestrator.domain.behavior;

import java.time.Duration;
import java.time.Instant;

public class PersonalityStateManager {

    static final Duration LONELINESS_THRESHOLD = Duration.ofSeconds(30);
    private static final double SLEEP_BOREDOM_CAP = 0.3;

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

    public void applyPassiveDrift(PersonalityState state, Instant now) {
        boolean lonely = state.lastInteractionAt() == null
                || Duration.between(state.lastInteractionAt(), now)
                        .compareTo(LONELINESS_THRESHOLD) > 0;
        boolean sleeping = state.posture() == Posture.SLEEPING;
        double boredomGrowth = sleeping ? 0.0 : 0.01;
        state.apply(new PersonalityDelta(sleeping ? 0.05 : 0,
                lonely ? -0.005 : 0,
                boredomGrowth,
                sleeping ? 0 : 0.005,
                lonely ? 0.01 : 0,
                0));
        state.driftContentmentTowardNeutral(0.02);
    }

    public void applyEvent(PersonalityState state, BehaviorEvent event, Instant now) {
        switch (event) {
            case OWNER_PETTED -> state.apply(new PersonalityDelta(0, 0.15, 0, 0, -0.10, 0));
            case OWNER_CALLED_OUT -> state.apply(new PersonalityDelta(0, 0, 0, 0.10, -0.20, 0));
            case OWNER_PLAYED -> state.apply(new PersonalityDelta(-0.15, 0.20, -0.30, 0, 0, 0));
            case PICKED_UP, FELL_OVER -> {
                state.apply(new PersonalityDelta(0, 0, 0, 0.10, 0, -0.10));
                state.setPosture(Posture.LYING);
            }
            case LOW_BATTERY -> state.apply(new PersonalityDelta(-0.30, 0, 0, 0, 0, 0));
        }
        if (event.ownerInteraction()) {
            state.recordInteraction(now);
        }
    }
}

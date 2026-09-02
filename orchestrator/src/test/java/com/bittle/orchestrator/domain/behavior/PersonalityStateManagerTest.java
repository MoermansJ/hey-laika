package com.bittle.orchestrator.domain.behavior;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.stream.IntStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PersonalityStateManagerTest {

    private final PersonalityStateManager manager = new PersonalityStateManager();
    private PersonalityState state;

    @BeforeEach
    void setUp() {
        state = new PersonalityState();
    }

    @Test
    void givenStandingRobot_whenSitDownSucceeds_thenImpactAndPostureAreApplied() {
        double energyBefore = state.energy();

        manager.onActionCompleted(state, Action.SIT_DOWN, true, Instant.now());

        assertThat(state.posture()).isEqualTo(Posture.SITTING);
        assertThat(state.energy()).isEqualTo(energyBefore + 0.03);
        assertThat(state.lastAction()).isEqualTo(Action.SIT_DOWN);
        assertThat(state.totalActionsThisSession()).isEqualTo(1);
    }

    @Test
    void givenStandingRobot_whenSitDownFails_thenOnlyTheLogChanges() {
        double energyBefore = state.energy();

        manager.onActionCompleted(state, Action.SIT_DOWN, false, Instant.now());

        assertThat(state.posture()).isEqualTo(Posture.STANDING);
        assertThat(state.energy()).isEqualTo(energyBefore);
        assertThat(state.totalActionsThisSession()).isEqualTo(1);
    }

    @Test
    void givenRepeatedOpposingEvents_whenApplied_thenValuesStayWithinUnitRange() {
        IntStream.range(0, 10).forEach(i -> {
            manager.applyEvent(state, BehaviorEvent.OWNER_PLAYED, Instant.now());
            manager.applyEvent(state, BehaviorEvent.LOW_BATTERY, Instant.now());
        });

        assertThat(state.happiness()).isBetween(0.0, 1.0);
        assertThat(state.energy()).isBetween(0.0, 1.0);
        assertThat(state.boredom()).isBetween(0.0, 1.0);
    }

    @Test
    void givenTiredBoredLyingRobot_whenSleepSucceeds_thenEnergyIsRestoredAndBoredomCapped() {
        manager.onActionCompleted(state, Action.LIE_DOWN, true, Instant.now());
        // Make it tired and bored before the nap.
        state.apply(new PersonalityDelta(-0.6, 0, 0.5, 0, 0, 0));
        double energyBefore = state.energy();

        manager.onActionCompleted(state, Action.SLEEP, true, Instant.now());

        assertThat(state.posture()).isEqualTo(Posture.SLEEPING);
        assertThat(state.energy()).isEqualTo(Math.min(1.0, energyBefore + 0.40));
        assertThat(state.boredom()).isLessThanOrEqualTo(0.3);
    }

    @Test
    void givenSleepingRobot_whenPassiveDriftApplied_thenEnergyRecoversAndBoredomIsUnchanged() {
        state.apply(new PersonalityDelta(-0.5, 0, 0, 0, 0, 0)); // tired first
        manager.onActionCompleted(state, Action.LIE_DOWN, true, Instant.now());
        manager.onActionCompleted(state, Action.SLEEP, true, Instant.now());
        double energyBefore = state.energy();
        double boredomBefore = state.boredom();

        manager.applyPassiveDrift(state, Instant.now());

        assertThat(state.energy()).isGreaterThan(energyBefore);
        assertThat(state.boredom()).isEqualTo(boredomBefore); // no boredom growth asleep
    }

    @Test
    void givenNoInteractionPastLonelinessThreshold_whenPassiveDriftApplied_thenHungerGrows() {
        double hungerBefore = state.hunger();
        var later = Instant.now().plus(PersonalityStateManager.LONELINESS_THRESHOLD)
                .plusSeconds(5);

        manager.applyPassiveDrift(state, later);

        assertThat(state.hunger()).isGreaterThan(hungerBefore);
    }

    @Test
    void givenContentRobot_whenOwnerPets_thenHappinessRisesAndInteractionIsRecorded() {
        var now = Instant.now().plusSeconds(60);
        double happinessBefore = state.happiness();

        manager.applyEvent(state, BehaviorEvent.OWNER_PETTED, now);

        assertThat(state.happiness()).isEqualTo(Math.min(1.0, happinessBefore + 0.15));
        assertThat(state.lastInteractionAt()).isEqualTo(now);
    }

    @Test
    void givenStandingRobot_whenPickedUp_thenPostureResyncsToLying() {
        assertThat(state.posture()).isEqualTo(Posture.STANDING);

        manager.applyEvent(state, BehaviorEvent.PICKED_UP, Instant.now());

        assertThat(state.posture()).isEqualTo(Posture.LYING);
    }
}

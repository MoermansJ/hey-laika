package com.bittle.orchestrator.domain.behavior;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.EnumSet;
import java.util.Random;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class RuleBasedDecisionEngineTest {

    private final RuleBasedDecisionEngine engine = new RuleBasedDecisionEngine(false);
    private final PersonalityStateManager manager = new PersonalityStateManager();

    @Test
    void givenContentStandingRobot_whenIdleCycleDisabled_thenItIdlesCalmly() {
        var state = new PersonalityState(); // content defaults, standing

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.IDLE_CALM);
    }

    @Test
    void givenExhaustedStandingRobot_whenDeciding_thenItLiesDownFirst() {
        var state = new PersonalityState();
        state.apply(new PersonalityDelta(-0.5, 0, 0, 0, 0, 0)); // energy 0.1

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.LIE_DOWN);
    }

    @Test
    void givenExhaustedLyingRobot_whenDeciding_thenItSleeps() {
        var state = new PersonalityState();
        state.setPosture(Posture.LYING);
        state.apply(new PersonalityDelta(-0.5, 0, 0, 0, 0, 0));

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.SLEEP);
    }

    @Test
    void givenSleepingRobot_whenEnergyIsStillLow_thenItKeepsResting() {
        var state = new PersonalityState();
        state.setPosture(Posture.SLEEPING);
        state.apply(new PersonalityDelta(-0.3, 0, 0, 0, 0, 0)); // energy 0.3

        var decision = engine.decide(state);

        assertThat(decision.action()).isNull();
    }

    @Test
    void givenSleepingRobot_whenEnergyHasRecovered_thenItWakesUp() {
        var state = new PersonalityState();
        state.setPosture(Posture.SLEEPING);
        state.apply(new PersonalityDelta(0.1, 0, 0, 0, 0, 0)); // energy 0.7

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.WAKE_UP);
    }

    @Test
    void givenBoredEnergeticStandingRobot_whenDeciding_thenItPlays() {
        var state = new PersonalityState();
        state.apply(new PersonalityDelta(0.2, 0, 0.5, 0, 0, 0)); // energy .8, boredom .9

        var decision = engine.decide(state);

        assertThat(decision.action())
                .isIn(Action.PLAY_BOW, Action.SPIN, Action.BACKFLIP);
    }

    @Test
    void givenBoredLyingRobot_whenDeciding_thenItStandsUpFirst() {
        var state = new PersonalityState();
        state.setPosture(Posture.LYING);
        state.apply(new PersonalityDelta(0.2, 0, 0.5, 0, 0, 0));

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.STAND_UP);
    }

    @Test
    void givenRandomStates_whenDeciding_thenEveryActionIsValidForItsPosture() {
        var random = new Random(42);

        IntStream.range(0, 500).forEach(cycle -> {
            var state = randomState(random);

            var decision = engine.decide(state);

            if (decision.action() != null) {
                assertThat(decision.action().validFor(state.posture(), state.energy()))
                        .as("cycle %d: %s from %s (energy %.2f)", cycle,
                                decision.action(), state.posture(), state.energy())
                        .isTrue();
            }
        });
    }

    /**
     * With behavior.idle-cycle enabled, the active behavior is the stationary
     * cycle: sit → look around (low) → stand → stand a moment →
     * look around (slow) → sit, with variable-length chains. No stretch.
     */
    @Test
    void givenIdleCycleEnabled_whenRunningSixtySteps_thenOnlyCycleActionsOccurInOrder() {
        var cycleEngine = new RuleBasedDecisionEngine(true);
        var cycleActions = EnumSet.of(Action.SIT_DOWN, Action.LOOK_AROUND_LOW,
                Action.STAND_UP, Action.IDLE_CALM, Action.LOOK_AROUND_SLOW);
        var state = new PersonalityState(); // content defaults, standing

        var seen = IntStream.range(0, 60)
                .mapToObj(step -> {
                    var action = cycleEngine.decide(state).action();
                    assertThat(action).as("cycle step %d", step).isNotNull().isIn(cycleActions);
                    manager.onActionCompleted(state, action, true, Instant.now());
                    return action;
                })
                .toList();

        assertThat(seen).containsAll(cycleActions);
        IntStream.range(1, seen.size())
                .filter(i -> seen.get(i) == Action.LOOK_AROUND_SLOW)
                .forEach(i -> assertThat(seen.get(i - 1))
                        .as("slow look-around follows the standing hold (or chains)")
                        .isIn(Action.IDLE_CALM, Action.LOOK_AROUND_SLOW));
    }

    /** Regression for the v1.0 nap-loop: an exhausted robot must sleep, recover and wake. */
    @Test
    void givenExhaustedStandingRobot_whenCyclingWithDrift_thenItSleepsRecoversAndWakes() {
        var state = new PersonalityState();
        state.apply(new PersonalityDelta(-0.5, 0, 0, 0, 0, 0)); // exhausted, standing

        // Stateful with an early exit on wake-up, so a plain loop reads clearer than a stream.
        boolean slept = false;
        boolean woke = false;
        for (int cycle = 0; cycle < 40 && !woke; cycle++) {
            var action = engine.decide(state).action();
            if (action != null) {
                manager.onActionCompleted(state, action, true, Instant.now());
                slept |= action == Action.SLEEP;
                woke = action == Action.WAKE_UP;
            }
            manager.applyPassiveDrift(state, Instant.now());
        }

        assertThat(slept).as("robot should have gone to sleep").isTrue();
        assertThat(woke).as("robot should have woken up within 40 cycles").isTrue();
        assertThat(state.energy()).isGreaterThanOrEqualTo(0.55);
        assertThat(state.posture()).isEqualTo(Posture.LYING);
    }

    private static PersonalityState randomState(Random random) {
        var state = new PersonalityState();
        state.setPosture(Posture.values()[random.nextInt(Posture.values().length)]);
        state.apply(new PersonalityDelta(signedUnit(random), signedUnit(random),
                signedUnit(random), signedUnit(random), signedUnit(random), signedUnit(random)));
        return state;
    }

    private static double signedUnit(Random random) {
        return random.nextDouble() * 2 - 1;
    }
}

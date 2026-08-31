package com.bittle.orchestrator.behavior;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class RuleBasedDecisionEngineTest {

    private static RuleBasedDecisionEngine engine(boolean idleCycle) {
        return new RuleBasedDecisionEngine(new BehaviorProperties(
                2500, 5000, 5000, 200, false, false, idleCycle));
    }

    private final RuleBasedDecisionEngine engine = engine(false);
    private final PersonalityStateManager manager = new PersonalityStateManager();

    @Test
    void contentRobotIdlesWhenCycleDisabled() {
        var state = new PersonalityState(); // content defaults, standing
        assertThat(engine.decide(state).action()).isEqualTo(Action.IDLE_CALM);
    }

    @Test
    void exhaustedStandingRobotLiesDownFirst() {
        var state = new PersonalityState();
        state.apply(new PersonalityDelta(-0.5, 0, 0, 0, 0, 0)); // energy 0.1

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.LIE_DOWN);
    }

    @Test
    void exhaustedLyingRobotSleeps() {
        var state = new PersonalityState();
        state.setPosture(Posture.LYING);
        state.apply(new PersonalityDelta(-0.5, 0, 0, 0, 0, 0));

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.SLEEP);
    }

    @Test
    void sleepingRobotRestsUntilRecovered() {
        var state = new PersonalityState();
        state.setPosture(Posture.SLEEPING);
        state.apply(new PersonalityDelta(-0.3, 0, 0, 0, 0, 0)); // energy 0.3

        assertThat(engine.decide(state).action()).isNull();

        state.apply(new PersonalityDelta(0.4, 0, 0, 0, 0, 0)); // energy 0.7
        assertThat(engine.decide(state).action()).isEqualTo(Action.WAKE_UP);
    }

    @Test
    void boredEnergeticStandingRobotPlays() {
        var state = new PersonalityState();
        state.apply(new PersonalityDelta(0.2, 0, 0.5, 0, 0, 0)); // energy .8, boredom .9

        var decision = engine.decide(state);

        assertThat(decision.action())
                .isIn(Action.PLAY_BOW, Action.SPIN, Action.BACKFLIP);
    }

    @Test
    void boredLyingRobotStandsUpFirst() {
        var state = new PersonalityState();
        state.setPosture(Posture.LYING);
        state.apply(new PersonalityDelta(0.2, 0, 0.5, 0, 0, 0));

        var decision = engine.decide(state);

        assertThat(decision.action()).isEqualTo(Action.STAND_UP);
    }

    @Test
    void decisionsAreAlwaysValidForCurrentPosture() {
        var random = new java.util.Random(42);
        for (int i = 0; i < 500; i++) {
            var state = new PersonalityState();
            state.setPosture(Posture.values()[random.nextInt(Posture.values().length)]);
            state.apply(new PersonalityDelta(random.nextDouble() * 2 - 1,
                    random.nextDouble() * 2 - 1, random.nextDouble() * 2 - 1,
                    random.nextDouble() * 2 - 1, random.nextDouble() * 2 - 1,
                    random.nextDouble() * 2 - 1));

            var decision = engine.decide(state);

            if (decision.action() != null) {
                assertThat(decision.action().validFor(state.posture(), state.energy()))
                        .as("cycle %d: %s from %s (energy %.2f)", i,
                                decision.action(), state.posture(), state.energy())
                        .isTrue();
            }
        }
    }

    /**
     * With behavior.idle-cycle enabled, the active behavior is the stationary
     * cycle: sit → look around (low) → stand → stand a moment →
     * look around (slow) → sit, with variable-length chains. No stretch.
     */
    @Test
    void idleCycleRunsWhenEnabled() {
        var cycleEngine = engine(true);
        var cycleActions = java.util.EnumSet.of(Action.SIT_DOWN, Action.LOOK_AROUND_LOW,
                Action.STAND_UP, Action.IDLE_CALM, Action.LOOK_AROUND_SLOW);
        var state = new PersonalityState(); // content defaults, standing
        var seen = new java.util.ArrayList<Action>();

        for (int i = 0; i < 60; i++) {
            var decision = cycleEngine.decide(state);
            assertThat(decision.action()).as("cycle step %d", i).isNotNull();
            assertThat(cycleActions).contains(decision.action());
            seen.add(decision.action());
            manager.onActionCompleted(state, decision.action(), true, Instant.now());
        }

        assertThat(seen).containsAll(cycleActions);
        for (int i = 1; i < seen.size(); i++) {
            if (seen.get(i) == Action.LOOK_AROUND_SLOW) {
                assertThat(seen.get(i - 1))
                        .as("slow look-around follows the standing hold (or chains)")
                        .isIn(Action.IDLE_CALM, Action.LOOK_AROUND_SLOW);
            }
        }
    }

    /** Regression for the v1.0 nap-loop: an exhausted robot must sleep, recover and wake. */
    @Test
    void exhaustedRobotSleepsRecoversAndWakes() {
        var state = new PersonalityState();
        state.apply(new PersonalityDelta(-0.5, 0, 0, 0, 0, 0)); // exhausted, standing

        boolean slept = false;
        boolean woke = false;
        for (int cycle = 0; cycle < 40 && !woke; cycle++) {
            var decision = engine.decide(state);
            if (decision.action() != null) {
                manager.onActionCompleted(state, decision.action(), true, Instant.now());
                slept |= decision.action() == Action.SLEEP;
                woke = decision.action() == Action.WAKE_UP;
            }
            manager.applyPassiveDrift(state, Instant.now());
        }

        assertThat(slept).as("robot should have gone to sleep").isTrue();
        assertThat(woke).as("robot should have woken up within 40 cycles").isTrue();
        assertThat(state.energy()).isGreaterThanOrEqualTo(0.55);
        assertThat(state.posture()).isEqualTo(Posture.LYING);
    }
}

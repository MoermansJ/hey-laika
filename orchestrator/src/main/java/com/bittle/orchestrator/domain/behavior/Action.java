package com.bittle.orchestrator.domain.behavior;

import static com.bittle.orchestrator.domain.behavior.Posture.LYING;
import static com.bittle.orchestrator.domain.behavior.Posture.SITTING;
import static com.bittle.orchestrator.domain.behavior.Posture.SLEEPING;
import static com.bittle.orchestrator.domain.behavior.Posture.STANDING;

import java.util.EnumSet;
import java.util.Set;

/**
 * The behavior catalog. Each action carries its full definition: wire id,
 * estimated duration, the postures it can start from, the posture it leaves
 * the robot in (null = unchanged), its personality impact and a minimum-energy
 * safety gate. Prerequisites are enforced by filtering with
 * {@link #validFor(Posture, double)} before any decision is made.
 */
public enum Action {

    // Movement
    WALK_SLOW("walk_slow", 3000, EnumSet.of(STANDING), null,
            new PersonalityDelta(-0.05, 0, -0.15, -0.05, 0, 0.03), 0.2),
    WALK_FAST("walk_fast", 2000, EnumSet.of(STANDING), null,
            new PersonalityDelta(-0.05, 0, -0.15, -0.05, 0, 0.03), 0.3),
    STAND_UP("stand_up", 1000, EnumSet.of(SITTING, LYING), STANDING,
            new PersonalityDelta(-0.01, 0, 0, 0, 0, 0), 0),
    SIT_DOWN("sit_down", 1500, EnumSet.of(STANDING), SITTING,
            new PersonalityDelta(0.03, 0, 0.08, 0, 0, -0.02), 0),
    LIE_DOWN("lie_down", 2000, EnumSet.of(STANDING, SITTING), LYING,
            new PersonalityDelta(0.05, 0, 0.05, 0, 0, 0), 0),

    // Head / attention
    LOOK_LEFT("look_left", 800, EnumSet.of(STANDING, SITTING), null,
            new PersonalityDelta(-0.01, 0, -0.05, -0.08, 0, 0), 0),
    LOOK_RIGHT("look_right", 800, EnumSet.of(STANDING, SITTING), null,
            new PersonalityDelta(-0.01, 0, -0.05, -0.08, 0, 0), 0),
    LOOK_UP("look_up", 800, EnumSet.of(STANDING, SITTING), null,
            new PersonalityDelta(-0.01, 0, -0.05, -0.08, 0, 0), 0),
    /** Small, quick side-to-side head sweeps while sitting (idle cycle). */
    LOOK_AROUND_LOW("look_around_low", 2200, EnumSet.of(SITTING), null,
            new PersonalityDelta(-0.01, 0, -0.06, -0.06, 0, 0.01), 0),
    /** Wide, slow stepped head sweeps while standing (idle cycle). */
    LOOK_AROUND_SLOW("look_around_slow", 3600, EnumSet.of(STANDING), null,
            new PersonalityDelta(-0.02, 0, -0.08, -0.08, 0, 0.02), 0),
    /** Morning-stretch posture; part of the idle cycle, distinct from play. */
    STRETCH("stretch", 2600, EnumSet.of(STANDING), null,
            new PersonalityDelta(-0.03, 0.03, -0.10, 0, 0, 0.06), 0.1),

    // Interactive / play
    PLAY_BOW("play_bow", 1500, EnumSet.of(STANDING), null,
            new PersonalityDelta(-0.10, 0.10, -0.25, 0, 0, 0.15), 0.3),
    BACKFLIP("backflip", 2000, EnumSet.of(STANDING), null,
            new PersonalityDelta(-0.10, 0.10, -0.25, 0, 0, 0.15), 0.5),
    SPIN("spin", 2000, EnumSet.of(STANDING), null,
            new PersonalityDelta(-0.10, 0.10, -0.25, 0, 0, 0.15), 0.3),

    // Rest
    IDLE_CALM("idle_calm", 1000, EnumSet.of(STANDING, SITTING, LYING), null,
            new PersonalityDelta(0.02, 0, 0.03, 0, 0, 0), 0),
    SLEEP("sleep", 5000, EnumSet.of(LYING), SLEEPING,
            new PersonalityDelta(0.40, 0, 0, -0.10, 0, 0.05), 0),
    WAKE_UP("wake_up", 1000, EnumSet.of(SLEEPING), LYING,
            new PersonalityDelta(0, 0.03, 0, 0.05, 0, 0), 0),

    // Social
    SEEK_ATTENTION("seek_attention", 2000, EnumSet.of(STANDING, SITTING), null,
            new PersonalityDelta(-0.03, -0.02, 0, 0, -0.05, -0.05), 0);

    private final String actionId;
    private final long durationMs;
    private final Set<Posture> validFrom;
    private final Posture resultingPosture;
    private final PersonalityDelta impact;
    private final double minEnergy;

    Action(String actionId, long durationMs, Set<Posture> validFrom,
           Posture resultingPosture, PersonalityDelta impact, double minEnergy) {
        this.actionId = actionId;
        this.durationMs = durationMs;
        this.validFrom = validFrom;
        this.resultingPosture = resultingPosture;
        this.impact = impact;
        this.minEnergy = minEnergy;
    }

    public String actionId() {
        return actionId;
    }

    public long durationMs() {
        return durationMs;
    }

    public PersonalityDelta impact() {
        return impact;
    }

    public Posture postureAfter(Posture current) {
        return resultingPosture == null ? current : resultingPosture;
    }

    public boolean validFor(Posture posture, double energy) {
        return validFrom.contains(posture) && energy >= minEnergy;
    }

    public static java.util.List<Action> validActions(Posture posture, double energy) {
        return java.util.Arrays.stream(values())
                .filter(a -> a.validFor(posture, energy))
                .toList();
    }

    public static Action fromActionId(String actionId) {
        for (var action : values()) {
            if (action.actionId.equalsIgnoreCase(actionId)) {
                return action;
            }
        }
        throw new IllegalArgumentException("Unknown action: " + actionId);
    }
}

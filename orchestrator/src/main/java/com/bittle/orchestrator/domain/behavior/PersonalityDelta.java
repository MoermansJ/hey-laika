package com.bittle.orchestrator.domain.behavior;

/** Change applied to a {@link PersonalityState} when an action completes or an event fires. */
public record PersonalityDelta(double energy, double happiness, double boredom,
                               double curiosity, double hunger, double contentment) {

    public static final PersonalityDelta NONE = new PersonalityDelta(0, 0, 0, 0, 0, 0);
}

package com.bittle.orchestrator.domain.behavior;

public record PersonalityDelta(double energy, double happiness, double boredom,
                               double curiosity, double hunger, double contentment) {

    public static final PersonalityDelta NONE = new PersonalityDelta(0, 0, 0, 0, 0, 0);
}

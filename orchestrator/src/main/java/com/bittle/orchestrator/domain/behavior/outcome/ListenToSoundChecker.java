package com.bittle.orchestrator.domain.behavior.outcome;

import java.util.Locale;
import java.util.Objects;

/** listen_to_sound: the peak audio amplitude rose (the robot oriented toward the sound). */
public class ListenToSoundChecker implements GoalOutcomeChecker {

    public static final String GOAL = "listen_to_sound";

    private final OutcomeThresholds thresholds;

    public ListenToSoundChecker(OutcomeThresholds thresholds) {
        this.thresholds = Objects.requireNonNull(thresholds, "thresholds");
    }

    @Override
    public String goal() {
        return GOAL;
    }

    @Override
    public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
        Double from = before.audioAmplitudePeak();
        Double to = after.audioAmplitudePeak();
        if (from == null || to == null) {
            return GoalCheck.undetermined("Insufficient audio data");
        }
        double delta = to - from;
        return Verdicts.judge(delta, thresholds.listenAmplitudeDelta(),
                thresholds.listenAmplitudeScale(), String.format(Locale.ROOT,
                        "Audio amplitude %s by %.2f (threshold: %.2f)",
                        delta >= 0 ? "increased" : "decreased", Math.abs(delta),
                        thresholds.listenAmplitudeDelta()));
    }
}

package com.bittle.orchestrator.domain.behavior.outcome;

import java.util.Locale;
import java.util.Objects;

/**
 * bark: after the run the audio peak is loud enough and, when the spectrum's
 * dominant frequency is known, it lies in the bark band.
 */
public class BarkChecker implements GoalOutcomeChecker {

    public static final String GOAL = "bark";

    private final OutcomeThresholds thresholds;

    public BarkChecker(OutcomeThresholds thresholds) {
        this.thresholds = Objects.requireNonNull(thresholds, "thresholds");
    }

    @Override
    public String goal() {
        return GOAL;
    }

    @Override
    public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
        Double peak = after.audioAmplitudePeak();
        if (peak == null) {
            return GoalCheck.undetermined("Insufficient audio data");
        }
        Double hz = after.audioDominantHz();
        if (hz != null && peak >= thresholds.barkAmplitude()
                && (hz < thresholds.barkMinHz() || hz > thresholds.barkMaxHz())) {
            return GoalCheck.failed(Math.min(1.0, peak / thresholds.barkAmplitudeScale()),
                    String.format(Locale.ROOT,
                            "Loud sound (peak %.2f) at %.0f Hz is outside the bark band "
                                    + "%.0f-%.0f Hz", peak, hz, thresholds.barkMinHz(),
                            thresholds.barkMaxHz()));
        }
        String spectrum = hz == null ? "" : String.format(Locale.ROOT, " at %.0f Hz", hz);
        return Verdicts.judge(peak, thresholds.barkAmplitude(), thresholds.barkAmplitudeScale(),
                String.format(Locale.ROOT, "Audio peak %.2f%s (threshold: %.2f)", peak,
                        spectrum, thresholds.barkAmplitude()));
    }
}

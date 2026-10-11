package com.bittle.orchestrator.domain.behavior.outcome;

/**
 * Tunable thresholds for the goal outcome checkers (AGENT-08). A run succeeds
 * when its measured change reaches the threshold; the matching {@code …Scale}
 * is the change that counts as a fully confident success.
 *
 * @param lookCentroidPx       camera motion centroid shift for look_* goals, pixels
 * @param lookCentroidScalePx  centroid shift for confidence 1.0, pixels
 * @param lookImuDeg           head pitch/yaw change for look_* goals when no centroid, degrees
 * @param lookImuScaleDeg      pitch/yaw change for confidence 1.0, degrees
 * @param moveForwardCm        forward odometry distance for move_forward, centimetres
 * @param moveForwardScaleCm   distance for confidence 1.0, centimetres
 * @param listenAmplitudeDelta rise in peak audio amplitude for listen_to_sound (0.0-1.0)
 * @param listenAmplitudeScale rise for confidence 1.0
 * @param barkAmplitude        peak audio amplitude after a bark (0.0-1.0)
 * @param barkAmplitudeScale   peak for confidence 1.0
 * @param barkMinHz            lowest dominant frequency that counts as a bark
 * @param barkMaxHz            highest dominant frequency that counts as a bark
 * @param tiltHeadDeg          head roll change for tilt_head, degrees
 * @param tiltHeadScaleDeg     roll change for confidence 1.0, degrees
 */
public record OutcomeThresholds(double lookCentroidPx, double lookCentroidScalePx,
                                double lookImuDeg, double lookImuScaleDeg,
                                double moveForwardCm, double moveForwardScaleCm,
                                double listenAmplitudeDelta, double listenAmplitudeScale,
                                double barkAmplitude, double barkAmplitudeScale,
                                double barkMinHz, double barkMaxHz,
                                double tiltHeadDeg, double tiltHeadScaleDeg) {

    public OutcomeThresholds {
        positive("lookCentroidPx", lookCentroidPx);
        positive("lookCentroidScalePx", lookCentroidScalePx);
        positive("lookImuDeg", lookImuDeg);
        positive("lookImuScaleDeg", lookImuScaleDeg);
        positive("moveForwardCm", moveForwardCm);
        positive("moveForwardScaleCm", moveForwardScaleCm);
        positive("listenAmplitudeDelta", listenAmplitudeDelta);
        positive("listenAmplitudeScale", listenAmplitudeScale);
        positive("barkAmplitude", barkAmplitude);
        positive("barkAmplitudeScale", barkAmplitudeScale);
        positive("barkMinHz", barkMinHz);
        positive("tiltHeadDeg", tiltHeadDeg);
        positive("tiltHeadScaleDeg", tiltHeadScaleDeg);
        if (barkMaxHz <= barkMinHz) {
            throw new IllegalArgumentException("barkMaxHz must be above barkMinHz");
        }
    }

    /** Defaults from AGENT_TOOL_COMPOSITION_DESIGN.md §3.2 where it gives them. */
    public static OutcomeThresholds defaults() {
        return new OutcomeThresholds(30, 100, 10, 30, 5, 20, 0.1, 0.3, 0.3, 0.6, 250, 2000,
                10, 30);
    }

    private static void positive(String name, double value) {
        if (!(value > 0) || Double.isInfinite(value)) {
            throw new IllegalArgumentException(name + " must be a positive number: " + value);
        }
    }
}

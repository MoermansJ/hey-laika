package com.bittle.orchestrator.domain.behavior.outcome;

import java.time.Instant;
import java.util.Objects;

/**
 * The robot's sensor state at one moment, as seen by goal outcome checkers
 * (AGENT_TOOL_COMPOSITION_DESIGN.md §3.1-3.2). Every reading is optional: a
 * missing sensor or a failed read is null, and checkers must treat null as
 * "insufficient data" rather than as a zero reading. Capturing and caching
 * snapshots is SensorStateService's job (AGENT-09).
 *
 * @param capturedAt         when the snapshot was taken
 * @param cameraFrame        latest camera frame (JPEG bytes), or null
 * @param odometryPosition   dead-reckoned position, or null
 * @param audioAmplitudePeak peak microphone amplitude, normalized 0.0-1.0, or null
 * @param headImu            head orientation from the IMU, or null
 * @param motionCentroid     centroid of camera motion in frame pixels (origin top-left,
 *                           y grows downward), or null when no motion was detected
 * @param audioDominantHz    dominant frequency of the loudest recent audio, or null
 */
public record SensorSnapshot(Instant capturedAt, byte[] cameraFrame,
                             Odometry odometryPosition, Double audioAmplitudePeak,
                             Imu headImu, Point motionCentroid, Double audioDominantHz) {

    public SensorSnapshot {
        Objects.requireNonNull(capturedAt, "capturedAt");
        cameraFrame = cameraFrame == null ? null : cameraFrame.clone();
    }

    /** Snapshot without the derived vision/audio features. */
    public SensorSnapshot(Instant capturedAt, byte[] cameraFrame, Odometry odometryPosition,
                          Double audioAmplitudePeak, Imu headImu) {
        this(capturedAt, cameraFrame, odometryPosition, audioAmplitudePeak, headImu, null, null);
    }

    /** A snapshot with no readings at all. */
    public static SensorSnapshot empty(Instant capturedAt) {
        return new SensorSnapshot(capturedAt, null, null, null, null, null, null);
    }

    @Override
    public byte[] cameraFrame() {
        return cameraFrame == null ? null : cameraFrame.clone();
    }

    public boolean hasCameraFrame() {
        return cameraFrame != null && cameraFrame.length > 0;
    }

    /** Dead-reckoned position: x/y in centimetres, heading in degrees (0 = +x, CCW positive). */
    public record Odometry(double xCm, double yCm, double headingDeg) {
    }

    /**
     * Head orientation in degrees: pitch positive nose-up, roll positive tilted right,
     * yaw positive turned left (counter-clockwise seen from above).
     */
    public record Imu(double pitchDeg, double rollDeg, double yawDeg) {
    }

    /** A position in the camera frame, in pixels (origin top-left, y grows downward). */
    public record Point(double x, double y) {
    }
}

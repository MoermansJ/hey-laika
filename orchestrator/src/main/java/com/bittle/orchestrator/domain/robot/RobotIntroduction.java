package com.bittle.orchestrator.domain.robot;

import java.time.Instant;

/**
 * The spoken self-introduction behind "Hey Laika, introduce yourself".
 *
 * <p>Owned here rather than in the adapter so per-robot profile text has one
 * durable home. The contract mirrors
 * {@link com.bittle.orchestrator.domain.behavior.RobotMode}: Postgres is the
 * source of truth, the orchestrator pushes every change down to the adapter,
 * and the adapter keeps only an in-memory mirror (see {@code dog/app/mode.py}).
 */
public record RobotIntroduction(String robotId, String text, Instant updatedAt, String updatedBy) {

    public static final int MAX_CHARS = 2000;

    /** Nothing stored yet: the adapter speaks its compiled DEFAULT_INTRODUCTION. */
    public static RobotIntroduction none(String robotId) {
        return new RobotIntroduction(robotId, "", Instant.EPOCH, "default");
    }

    public static RobotIntroduction of(String robotId, String text, String updatedBy) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("introduction must not be blank");
        }
        var trimmed = text.strip();
        if (trimmed.length() > MAX_CHARS) {
            throw new IllegalArgumentException(
                    "introduction must be at most " + MAX_CHARS + " characters");
        }
        return new RobotIntroduction(robotId, trimmed, Instant.now(), updatedBy);
    }

    public boolean stored() {
        return !text.isBlank();
    }
}

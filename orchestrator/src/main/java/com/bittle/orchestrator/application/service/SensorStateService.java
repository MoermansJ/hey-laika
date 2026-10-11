package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.NavigableMap;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Captures and caches robot sensor snapshots for goal outcome evaluation
 * (AGENT_TOOL_COMPOSITION_DESIGN.md Phase 3, AGENT-09). A snapshot is taken
 * when an agent run starts and again when it ends; the evaluator compares them.
 *
 * <p>Sources (the adapter's existing read endpoints; each one optional):
 * <ul>
 *   <li>{@code GET /senses} — {@code pose.x/y} (metres) and {@code pose.heading}
 *       → odometry position in centimetres</li>
 *   <li>{@code GET /ears} — {@code level.peak} (int16 RMS units) → audio amplitude
 *       peak normalized to 0.0-1.0</li>
 *   <li>{@code GET /eyes/snap} — latest JPEG → camera frame</li>
 * </ul>
 * A source that fails, is missing or returns something unreadable leaves its
 * reading null; capturing never throws. Head IMU, motion centroid and the
 * audio dominant frequency are not served by the adapter yet and stay null.
 *
 * <p>Snapshots are kept in memory per robot for the TTL (default 10 minutes)
 * and at most {@link #MAX_SNAPSHOTS_PER_ROBOT} per robot, oldest dropped first.
 */
public class SensorStateService {

    public static final Duration DEFAULT_TTL = Duration.ofMinutes(10);
    public static final int MAX_SNAPSHOTS_PER_ROBOT = 256;

    private static final Logger log = LoggerFactory.getLogger(SensorStateService.class);
    private static final double INT16_FULL_SCALE = 32768.0;

    private final Fleet fleet;
    private final RobotAdapterPort adapter;
    private final Clock clock;
    private final Duration ttl;
    private final Map<String, NavigableMap<Instant, SensorSnapshot>> cache =
            new ConcurrentHashMap<>();

    public SensorStateService(Fleet fleet, RobotAdapterPort adapter, Clock clock, Duration ttl) {
        this.fleet = Objects.requireNonNull(fleet, "fleet");
        this.adapter = Objects.requireNonNull(adapter, "adapter");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.ttl = Objects.requireNonNull(ttl, "ttl");
        if (ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException("ttl must be positive: " + ttl);
        }
    }

    /**
     * Read the robot's sensors now and cache the result. Unknown robots and
     * unreachable sensors give a snapshot with null readings (an unknown robot's
     * snapshot is not cached).
     */
    public SensorSnapshot captureSnapshot(String robotId) {
        Instant now = clock.instant();
        Robot robot;
        try {
            robot = fleet.get(robotId);
        } catch (RobotNotFoundException e) {
            log.warn("Sensor snapshot requested for unknown robot {}", robotId);
            return SensorSnapshot.empty(now);
        }
        Map<String, Object> senses = read(robotId, "senses",
                () -> adapter.get(robot, "/senses"));
        Map<String, Object> ears = read(robotId, "ears", () -> adapter.get(robot, "/ears"));
        var frame = read(robotId, "camera", () -> adapter.getBinary(robot, "/eyes/snap"));
        byte[] jpeg = frame != null && frame.body() != null && frame.body().length > 0
                && isImage(frame.contentType()) ? frame.body() : null;

        var snapshot = new SensorSnapshot(now, jpeg, odometry(senses), audioPeak(ears), null);
        store(robotId, snapshot);
        return snapshot;
    }

    /**
     * The snapshot that describes the robot at {@code timestamp}: the newest cached
     * one captured at or before it. Empty when none is cached (or it expired).
     */
    public Optional<SensorSnapshot> getSnapshotAt(String robotId, Instant timestamp) {
        Objects.requireNonNull(timestamp, "timestamp");
        evictExpired();
        var snapshots = cache.get(robotId);
        if (snapshots == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(snapshots.floorEntry(timestamp)).map(Map.Entry::getValue);
    }

    /** The newest cached snapshot for the robot, if any. */
    public Optional<SensorSnapshot> latestSnapshot(String robotId) {
        evictExpired();
        var snapshots = cache.get(robotId);
        if (snapshots == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(snapshots.lastEntry()).map(Map.Entry::getValue);
    }

    /** Drop every robot's snapshots captured strictly before {@code timestamp}. */
    public int invalidateSnapshotsBefore(Instant timestamp) {
        Objects.requireNonNull(timestamp, "timestamp");
        int removed = 0;
        for (var snapshots : cache.values()) {
            var old = snapshots.headMap(timestamp, false);
            removed += old.size();
            old.clear();
        }
        return removed;
    }

    /** Number of cached snapshots across all robots (for metrics and tests). */
    public int cachedCount() {
        return cache.values().stream().mapToInt(Map::size).sum();
    }

    private void store(String robotId, SensorSnapshot snapshot) {
        var snapshots = cache.computeIfAbsent(robotId, id -> new ConcurrentSkipListMap<>());
        snapshots.put(snapshot.capturedAt(), snapshot);
        while (snapshots.size() > MAX_SNAPSHOTS_PER_ROBOT) {
            snapshots.pollFirstEntry();
        }
        evictExpired();
    }

    private void evictExpired() {
        invalidateSnapshotsBefore(clock.instant().minus(ttl));
    }

    private <T> T read(String robotId, String source, Supplier<T> call) {
        try {
            return call.get();
        } catch (RuntimeException e) {
            log.debug("Sensor source {} unavailable for {}: {}", source, robotId, e.getMessage());
            return null;
        }
    }

    static SensorSnapshot.Odometry odometry(Map<String, Object> senses) {
        if (senses == null || !(senses.get("pose") instanceof Map<?, ?> pose)) {
            return null;
        }
        Double x = number(pose.get("x"));
        Double y = number(pose.get("y"));
        Double heading = number(pose.get("heading"));
        if (x == null || y == null) {
            return null;
        }
        return new SensorSnapshot.Odometry(x * 100.0, y * 100.0, heading == null ? 0.0 : heading);
    }

    static Double audioPeak(Map<String, Object> ears) {
        if (ears == null || !(ears.get("level") instanceof Map<?, ?> level)) {
            return null;
        }
        Double peak = number(level.get("peak"));
        if (peak == null) {
            return null;
        }
        return Math.max(0.0, Math.min(1.0, peak / INT16_FULL_SCALE));
    }

    private static boolean isImage(String contentType) {
        return contentType != null && contentType.toLowerCase(Locale.ROOT).startsWith("image/");
    }

    private static Double number(Object raw) {
        if (raw instanceof Number n) {
            double value = n.doubleValue();
            return Double.isFinite(value) ? value : null;
        }
        return null;
    }
}

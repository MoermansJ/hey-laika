package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.port.out.LearnedPatternRepositoryPort;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.behavior.PatternStatus;
import com.bittle.orchestrator.domain.fleet.Fleet;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Read side of the learned-patterns store for the agent (AGENT-13): the active
 * patterns for a robot and goal, highest success rate first, cached briefly
 * (default 5 s) because Claude asks before every decision.
 */
public class LearnedPatternQueries {

    public static final Duration DEFAULT_TTL = Duration.ofSeconds(5);

    private final LearnedPatternRepositoryPort patterns;
    private final Fleet fleet;
    private final Clock clock;
    private final Duration ttl;
    private final Map<Key, Cached> cache = new ConcurrentHashMap<>();

    public LearnedPatternQueries(LearnedPatternRepositoryPort patterns, Fleet fleet, Clock clock,
                                 Duration ttl) {
        this.patterns = Objects.requireNonNull(patterns, "patterns");
        this.fleet = Objects.requireNonNull(fleet, "fleet");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.ttl = Objects.requireNonNull(ttl, "ttl");
    }

    /**
     * Active patterns for the goal, best first.
     *
     * @throws com.bittle.orchestrator.domain.fleet.RobotNotFoundException for an unknown robot
     * @throws IllegalArgumentException when the goal is blank
     */
    public List<LearnedPattern> activePatterns(String robotId, String goal) {
        fleet.get(robotId);
        if (goal == null || goal.isBlank()) {
            throw new IllegalArgumentException("goal is required");
        }
        Instant now = clock.instant();
        Key key = new Key(robotId, goal.strip());
        Cached cached = cache.get(key);
        if (cached != null && now.isBefore(cached.expiresAt())) {
            return cached.patterns();
        }
        List<LearnedPattern> fresh = patterns
                .findByRobotIdAndGoalOrderBySuccessRateDesc(key.robotId(), key.goal()).stream()
                .filter(p -> p.status() == PatternStatus.ACTIVE)
                .toList();
        cache.put(key, new Cached(fresh, now.plus(ttl)));
        return fresh;
    }

    private record Key(String robotId, String goal) {
    }

    private record Cached(List<LearnedPattern> patterns, Instant expiresAt) {
    }
}

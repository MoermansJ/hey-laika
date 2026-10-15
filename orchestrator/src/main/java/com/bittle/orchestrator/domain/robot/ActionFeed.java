package com.bittle.orchestrator.domain.robot;

import java.util.List;

/**
 * Every step the adapter's arbiter actually dispatched, newest first, each
 * tagged with the mode that generated it. This is a finer grain than the run
 * log ({@link ActivityLog} / behavior runs): Fruitfly and Roaming each submit
 * one long-running generator, so their individual decisions only show up here.
 */
public record ActionFeed(String robotId, List<Action> actions) {

    public record Action(String id, Double at, String tag, String action, String command,
                         String behavior, String runId, Integer step, String status,
                         Double endedAt) {
    }
}

package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.bittle.orchestrator.domain.behavior.outcome.GoalCheck;
import com.bittle.orchestrator.domain.behavior.outcome.GoalOutcomeChecker;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot;
import java.time.Clock;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Evaluates whether an agent run achieved its declared goal
 * (AGENT_TOOL_COMPOSITION_DESIGN.md §3.1, AGENT-07). Checkers register by goal;
 * the evaluator looks the goal up and turns the checker's {@link GoalCheck}
 * into an {@link OutcomeEvaluation} carrying {@link #EVALUATOR_VERSION} and the
 * evaluation time. A run without a goal, a goal without a checker, missing
 * snapshots or a failing checker all yield an undetermined outcome
 * ({@code success = null}, confidence 0.0) instead of an exception.
 */
public class GoalOutcomeEvaluator {

    public static final String EVALUATOR_VERSION = "1.0";

    private static final Logger log = LoggerFactory.getLogger(GoalOutcomeEvaluator.class);

    private final Map<String, GoalOutcomeChecker> checkers;
    private final Clock clock;

    public GoalOutcomeEvaluator(Collection<? extends GoalOutcomeChecker> checkers, Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
        Map<String, GoalOutcomeChecker> byGoal = new LinkedHashMap<>();
        for (GoalOutcomeChecker checker : checkers) {
            String goal = Objects.requireNonNull(checker.goal(),
                    () -> checker.getClass().getName() + ".goal()");
            GoalOutcomeChecker previous = byGoal.putIfAbsent(goal, checker);
            if (previous != null) {
                throw new IllegalArgumentException("Two outcome checkers for goal '" + goal + "': "
                        + previous.getClass().getName() + " and " + checker.getClass().getName());
            }
        }
        this.checkers = Collections.unmodifiableMap(byGoal);
        log.info("Goal outcome checkers registered: {}", this.checkers.keySet());
    }

    /** Evaluate a finished run against its declared goal. */
    public OutcomeEvaluation evaluateOutcome(BehaviorRunLog runLog, SensorSnapshot before,
                                             SensorSnapshot after) {
        Objects.requireNonNull(runLog, "runLog");
        String goal = runLog.goal();
        if (goal == null || goal.isBlank()) {
            return toOutcome(GoalCheck.undetermined("No goal declared"));
        }
        GoalOutcomeChecker checker = checkers.get(goal);
        if (checker == null) {
            log.debug("No outcome checker for goal {} (run {})", goal, runLog.id());
            return toOutcome(GoalCheck.undetermined("No evaluator registered for goal: " + goal));
        }
        if (before == null || after == null) {
            return toOutcome(GoalCheck.undetermined(
                    "Missing sensor snapshot " + (before == null ? "before" : "after") + " the run"));
        }
        GoalCheck check;
        try {
            check = checker.evaluate(before, after);
        } catch (RuntimeException e) {
            log.warn("Outcome checker for goal {} failed on run {}: {}", goal, runLog.id(),
                    e.toString(), e);
            return toOutcome(GoalCheck.undetermined("Evaluator failed: " + e.getMessage()));
        }
        if (check == null) {
            check = GoalCheck.undetermined("Evaluator returned no result");
        }
        OutcomeEvaluation outcome = toOutcome(check);
        log.debug("Run {} goal {} -> success={} confidence={} ({})", runLog.id(), goal,
                outcome.success(), outcome.confidence(), outcome.reason());
        return outcome;
    }

    /** True when a checker is registered for the goal. */
    public boolean supports(String goal) {
        return goal != null && checkers.containsKey(goal);
    }

    /** Goals that have a checker, in registration order. */
    public Set<String> registeredGoals() {
        return checkers.keySet();
    }

    private OutcomeEvaluation toOutcome(GoalCheck check) {
        return new OutcomeEvaluation(check.success(), check.confidence(), check.reason(),
                EVALUATOR_VERSION, clock.instant());
    }
}

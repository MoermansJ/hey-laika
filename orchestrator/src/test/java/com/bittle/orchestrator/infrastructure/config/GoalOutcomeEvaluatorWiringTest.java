package com.bittle.orchestrator.infrastructure.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.bittle.orchestrator.domain.behavior.outcome.GoalCheck;
import com.bittle.orchestrator.domain.behavior.outcome.GoalOutcomeChecker;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;

class GoalOutcomeEvaluatorWiringTest {

    @Test
    void givenCheckerBeans_whenEvaluatorBeanCreated_thenEachIsRegisteredByGoal() {
        Map<String, Object> checkers = Map.of(
                "barkChecker", new FixedChecker("bark"),
                "tiltChecker", new FixedChecker("tilt_head"));
        var beans = new StaticListableBeanFactory(checkers);

        var evaluator = new ApplicationConfig()
                .goalOutcomeEvaluator(beans.getBeanProvider(GoalOutcomeChecker.class));

        assertThat(evaluator.registeredGoals()).containsExactlyInAnyOrder("bark", "tilt_head");
    }

    @Test
    void givenNoCheckerBeans_whenEvaluatorBeanCreated_thenItStartsEmpty() {
        var beans = new StaticListableBeanFactory();

        var evaluator = new ApplicationConfig()
                .goalOutcomeEvaluator(beans.getBeanProvider(GoalOutcomeChecker.class));

        assertThat(evaluator.registeredGoals()).isEmpty();
    }

    private record FixedChecker(String goal) implements GoalOutcomeChecker {
        @Override
        public GoalCheck evaluate(SensorSnapshot before, SensorSnapshot after) {
            return GoalCheck.undetermined("test");
        }
    }
}

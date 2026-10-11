package com.bittle.orchestrator.infrastructure.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.bittle.orchestrator.domain.behavior.outcome.GoalOutcomeChecker;
import com.bittle.orchestrator.domain.behavior.outcome.OutcomeThresholds;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;

class OutcomeCheckerConfigTest {

    @Test
    void givenDefaultProperties_whenConverted_thenTheyEqualTheDomainDefaults() {
        var properties = new OutcomeCheckerProperties(30, 100, 10, 30, 5, 20, 0.1, 0.3, 0.3,
                0.6, 250, 2000, 10, 30);

        assertThat(properties.toThresholds()).isEqualTo(OutcomeThresholds.defaults());
    }

    @Test
    void givenAllCheckerBeans_whenEvaluatorCreated_thenEveryDesignGoalIsSupported() {
        var config = new OutcomeCheckerConfig();
        var thresholds = OutcomeThresholds.defaults();
        Map<String, Object> beans = new LinkedHashMap<>();
        beans.put("lookUpwardChecker", config.lookUpwardChecker(thresholds));
        beans.put("lookLeftChecker", config.lookLeftChecker(thresholds));
        beans.put("lookRightChecker", config.lookRightChecker(thresholds));
        beans.put("moveForwardChecker", config.moveForwardChecker(thresholds));
        beans.put("listenToSoundChecker", config.listenToSoundChecker(thresholds));
        beans.put("barkChecker", config.barkChecker(thresholds));
        beans.put("tiltHeadChecker", config.tiltHeadChecker(thresholds));

        var evaluator = new ApplicationConfig().goalOutcomeEvaluator(
                new StaticListableBeanFactory(beans).getBeanProvider(GoalOutcomeChecker.class));

        assertThat(evaluator.registeredGoals()).containsExactlyInAnyOrder("look_upward",
                "look_left", "look_right", "move_forward", "listen_to_sound", "bark",
                "tilt_head");
    }
}

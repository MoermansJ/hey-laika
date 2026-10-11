package com.bittle.orchestrator.infrastructure.config;

import com.bittle.orchestrator.domain.behavior.outcome.BarkChecker;
import com.bittle.orchestrator.domain.behavior.outcome.ListenToSoundChecker;
import com.bittle.orchestrator.domain.behavior.outcome.LookLeftChecker;
import com.bittle.orchestrator.domain.behavior.outcome.LookRightChecker;
import com.bittle.orchestrator.domain.behavior.outcome.LookUpwardChecker;
import com.bittle.orchestrator.domain.behavior.outcome.MoveForwardChecker;
import com.bittle.orchestrator.domain.behavior.outcome.OutcomeThresholds;
import com.bittle.orchestrator.domain.behavior.outcome.TiltHeadChecker;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * The goal outcome checkers (AGENT-08). Each is a GoalOutcomeChecker bean, so
 * the GoalOutcomeEvaluator in {@link ApplicationConfig} registers it by goal.
 */
@Configuration
public class OutcomeCheckerConfig {

    @Bean
    OutcomeThresholds outcomeThresholds(OutcomeCheckerProperties properties) {
        return properties.toThresholds();
    }

    @Bean
    LookUpwardChecker lookUpwardChecker(OutcomeThresholds thresholds) {
        return new LookUpwardChecker(thresholds);
    }

    @Bean
    LookLeftChecker lookLeftChecker(OutcomeThresholds thresholds) {
        return new LookLeftChecker(thresholds);
    }

    @Bean
    LookRightChecker lookRightChecker(OutcomeThresholds thresholds) {
        return new LookRightChecker(thresholds);
    }

    @Bean
    MoveForwardChecker moveForwardChecker(OutcomeThresholds thresholds) {
        return new MoveForwardChecker(thresholds);
    }

    @Bean
    ListenToSoundChecker listenToSoundChecker(OutcomeThresholds thresholds) {
        return new ListenToSoundChecker(thresholds);
    }

    @Bean
    BarkChecker barkChecker(OutcomeThresholds thresholds) {
        return new BarkChecker(thresholds);
    }

    @Bean
    TiltHeadChecker tiltHeadChecker(OutcomeThresholds thresholds) {
        return new TiltHeadChecker(thresholds);
    }
}

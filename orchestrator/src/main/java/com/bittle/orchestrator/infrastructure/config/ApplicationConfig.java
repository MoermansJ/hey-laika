package com.bittle.orchestrator.infrastructure.config;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.ConfiguredFleet;
import com.bittle.orchestrator.application.MetricsSettings;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.ActionExecutor;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.application.service.FleetSweep;
import com.bittle.orchestrator.application.service.OrchestratorMetricsSnapshot;
import com.bittle.orchestrator.domain.behavior.DecisionEngine;
import com.bittle.orchestrator.domain.behavior.PersonalityStateManager;
import com.bittle.orchestrator.domain.behavior.RuleBasedDecisionEngine;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.ComponentScan.Filter;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;

@Configuration
@ComponentScan(basePackages = "com.bittle.orchestrator.application.usecase",
        useDefaultFilters = false,
        includeFilters = @Filter(type = FilterType.REGEX, pattern = ".*UseCase"))
public class ApplicationConfig {

    @Bean
    ConfiguredFleet configuredFleet(RobotsProperties properties) {
        var definitions = properties.robots() == null
                ? List.<RobotsProperties.RobotDefinition>of()
                : properties.robots();
        return new ConfiguredFleet(definitions.stream()
                .map(d -> new Robot(d.id(), d.name(), d.type(), d.serviceUrl()))
                .toList());
    }

    @Bean
    BehaviorSettings behaviorSettings(BehaviorProperties properties) {
        return properties.toSettings();
    }

    @Bean
    MetricsSettings metricsSettings(MetricsProperties properties) {
        return properties.toSettings();
    }

    @Bean
    PersonalityStateManager personalityStateManager() {
        return new PersonalityStateManager();
    }

    @Bean
    DecisionEngine decisionEngine(BehaviorSettings settings) {
        return new RuleBasedDecisionEngine(settings.idleCycle());
    }

    @Bean
    FleetRegistry fleetRegistry() {
        return new FleetRegistry();
    }

    @Bean
    FleetSweep fleetSweep(FleetRegistry registry) {
        return new FleetSweep(registry);
    }

    @Bean
    ActionExecutor actionExecutor(RobotAdapterPort adapter, BehaviorSettings settings) {
        return new ActionExecutor(adapter, settings);
    }

    @Bean(destroyMethod = "shutdown")
    BehaviorLoops behaviorLoops(FleetRegistry registry, PersonalityStateManager stateManager,
                                DecisionEngine decisionEngine, ActionExecutor executor,
                                EventPublisherPort publisher, BehaviorSettings settings) {
        return new BehaviorLoops(registry, stateManager, decisionEngine, executor, publisher,
                settings);
    }

    @Bean
    OrchestratorMetricsSnapshot orchestratorMetricsSnapshot(OrchestratorMetricsPort metrics) {
        return new OrchestratorMetricsSnapshot(metrics);
    }
}

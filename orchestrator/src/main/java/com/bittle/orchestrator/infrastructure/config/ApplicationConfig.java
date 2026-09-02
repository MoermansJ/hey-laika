package com.bittle.orchestrator.infrastructure.config;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.ConfiguredFleet;
import com.bittle.orchestrator.application.MetricsSettings;
import com.bittle.orchestrator.application.port.in.BehaviorUseCase;
import com.bittle.orchestrator.application.port.in.FleetUseCase;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.FleetRepositoryPort;
import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort;
import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.ActionExecutor;
import com.bittle.orchestrator.application.service.BehaviorService;
import com.bittle.orchestrator.application.service.FleetBroadcastService;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.application.service.FleetService;
import com.bittle.orchestrator.application.service.FleetSyncService;
import com.bittle.orchestrator.application.service.MetricsService;
import com.bittle.orchestrator.application.service.RobotService;
import com.bittle.orchestrator.domain.behavior.DecisionEngine;
import com.bittle.orchestrator.domain.behavior.PersonalityStateManager;
import com.bittle.orchestrator.domain.behavior.RuleBasedDecisionEngine;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the framework-free domain and application objects as Spring beans.
 * Adapters are discovered by component scanning; everything inside the core
 * is constructed here so it carries no Spring annotations.
 */
@Configuration
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
    ActionExecutor actionExecutor(RobotAdapterPort adapter, BehaviorSettings settings) {
        return new ActionExecutor(adapter, settings);
    }

    @Bean(destroyMethod = "shutdown")
    BehaviorService behaviorService(FleetRegistry registry, PersonalityStateManager stateManager,
                                    DecisionEngine decisionEngine, ActionExecutor executor,
                                    EventPublisherPort publisher, BehaviorSettings settings) {
        return new BehaviorService(registry, stateManager, decisionEngine, executor, publisher,
                settings);
    }

    @Bean
    FleetService fleetService(FleetRegistry registry, RobotAdapterPort adapter) {
        return new FleetService(registry, adapter);
    }

    @Bean
    RobotService robotService(FleetRegistry registry, RobotAdapterPort adapter,
                              BehaviorUseCase behavior) {
        return new RobotService(registry, adapter, behavior);
    }

    @Bean
    FleetSyncService fleetSyncService(FleetRegistry registry, FleetRepositoryPort repository) {
        return new FleetSyncService(registry, repository);
    }

    @Bean
    MetricsService metricsService(FleetRegistry registry, RobotAdapterPort adapter,
                                  OrchestratorMetricsPort orchestratorMetrics,
                                  MetricsRollupRepositoryPort rollups, MetricsSettings settings) {
        return new MetricsService(registry, adapter, orchestratorMetrics, rollups, settings);
    }

    @Bean
    FleetBroadcastService fleetBroadcastService(FleetRegistry registry, FleetUseCase fleet,
                                                RobotAdapterPort adapter,
                                                EventPublisherPort publisher) {
        return new FleetBroadcastService(registry, fleet, adapter, publisher);
    }
}

package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.application.service.OrchestratorMetricsSnapshot;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RollupMetricsHourUseCase {

    private static final Logger log = LoggerFactory.getLogger(RollupMetricsHourUseCase.class);

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;
    private final OrchestratorMetricsSnapshot orchestrator;
    private final MetricsRollupRepositoryPort rollups;

    public RollupMetricsHourUseCase(FleetRegistry registry, RobotAdapterPort adapter,
                                    OrchestratorMetricsSnapshot orchestrator,
                                    MetricsRollupRepositoryPort rollups) {
        this.registry = registry;
        this.adapter = adapter;
        this.orchestrator = orchestrator;
        this.rollups = rollups;
    }

    public void execute() {
        var hourStart = Instant.now().truncatedTo(ChronoUnit.HOURS);
        rollups.save(OrchestratorMetricsSnapshot.ORCHESTRATOR_ID, hourStart, orchestrator.snapshot());
        registry.all().forEach(robot -> rollup(robot, hourStart));
    }

    private void rollup(Robot robot, Instant hourStart) {
        try {
            rollups.save(robot.id(), hourStart, adapter.metrics(robot));
        } catch (RuntimeException e) {
            log.warn("Metrics rollup skipped for {} (adapter unreachable): {}",
                    robot.id(), e.getMessage());
        }
    }
}

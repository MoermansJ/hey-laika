package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.InstanceIdentity;
import com.bittle.orchestrator.application.port.out.LeasePort;
import com.bittle.orchestrator.application.port.out.MetricsRollupRepositoryPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.OrchestratorMetricsSnapshot;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RollupMetricsHourUseCase {

    private static final Logger log = LoggerFactory.getLogger(RollupMetricsHourUseCase.class);
    private static final String LEASE_KEY = "metrics-rollup";
    private static final Duration LEASE_TTL = Duration.ofMinutes(50);

    private final Fleet fleet;
    private final RobotAdapterPort adapter;
    private final OrchestratorMetricsSnapshot orchestrator;
    private final MetricsRollupRepositoryPort rollups;
    private final LeasePort leases;
    private final InstanceIdentity identity;

    public RollupMetricsHourUseCase(Fleet fleet, RobotAdapterPort adapter,
                                    OrchestratorMetricsSnapshot orchestrator,
                                    MetricsRollupRepositoryPort rollups, LeasePort leases,
                                    InstanceIdentity identity) {
        this.fleet = fleet;
        this.adapter = adapter;
        this.orchestrator = orchestrator;
        this.rollups = rollups;
        this.leases = leases;
        this.identity = identity;
    }

    public void execute() {
        if (!leases.acquire(LEASE_KEY, identity.id(), LEASE_TTL)) {
            log.info("Metrics rollup skipped on {}: another instance holds the rollup lease",
                    identity.id());
            return;
        }
        var hourStart = Instant.now().truncatedTo(ChronoUnit.HOURS);
        rollups.save(OrchestratorMetricsSnapshot.ORCHESTRATOR_ID, hourStart, orchestrator.snapshot());
        fleet.all().forEach(robot -> rollup(robot, hourStart));
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

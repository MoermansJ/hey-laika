package com.bittle.orchestrator.adapter.in.scheduling;

import com.bittle.orchestrator.application.port.in.MetricsUseCase;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Persists the hourly metrics rollup at the top of every hour. */
@Component
public class MetricsRollupScheduler {

    private final MetricsUseCase metrics;

    public MetricsRollupScheduler(MetricsUseCase metrics) {
        this.metrics = metrics;
    }

    @Scheduled(cron = "0 0 * * * *")
    public void rollup() {
        metrics.rollupHour();
    }
}

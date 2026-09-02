package com.bittle.orchestrator.adapter.in.scheduling;

import com.bittle.orchestrator.application.usecase.RollupMetricsHourUseCase;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MetricsRollupScheduler {

    private final RollupMetricsHourUseCase rollupHour;

    public MetricsRollupScheduler(RollupMetricsHourUseCase rollupHour) {
        this.rollupHour = rollupHour;
    }

    @Scheduled(cron = "0 0 * * * *")
    public void rollup() {
        rollupHour.execute();
    }
}

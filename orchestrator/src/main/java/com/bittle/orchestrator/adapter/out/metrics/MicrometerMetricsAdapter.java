package com.bittle.orchestrator.adapter.out.metrics;

import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class MicrometerMetricsAdapter implements OrchestratorMetricsPort {

    static final String ADAPTER_UNAVAILABLE_COUNTER = "bittle.adapter.unavailable";

    private final MeterRegistry meterRegistry;

    public MicrometerMetricsAdapter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public HttpStats httpStats() {
        var timers = meterRegistry.find("http.server.requests").timers();
        long count = timers.stream().mapToLong(Timer::count).sum();
        double totalMs = timers.stream()
                .mapToDouble(timer -> timer.totalTime(TimeUnit.MILLISECONDS)).sum();
        double maxMs = timers.stream()
                .mapToDouble(timer -> timer.max(TimeUnit.MILLISECONDS)).max().orElse(0.0);
        return new HttpStats(count, totalMs, maxMs);
    }

    @Override
    public long adapterUnavailableCount() {
        return (long) meterRegistry.counter(ADAPTER_UNAVAILABLE_COUNTER).count();
    }

    @Override
    public void recordAdapterUnavailable() {
        meterRegistry.counter(ADAPTER_UNAVAILABLE_COUNTER).increment();
    }
}

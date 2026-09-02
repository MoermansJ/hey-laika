package com.bittle.orchestrator.adapter.in.startup;

import com.bittle.orchestrator.application.ConfiguredFleet;
import com.bittle.orchestrator.application.port.in.BehaviorUseCase;
import com.bittle.orchestrator.application.port.in.SyncFleetUseCase;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/** At boot: sync the configured fleet, then auto-start behavior loops if configured. */
@Component
public class FleetInitializer implements ApplicationRunner {

    private final ConfiguredFleet configuredFleet;
    private final SyncFleetUseCase syncFleet;
    private final BehaviorUseCase behavior;

    public FleetInitializer(ConfiguredFleet configuredFleet, SyncFleetUseCase syncFleet,
                            BehaviorUseCase behavior) {
        this.configuredFleet = configuredFleet;
        this.syncFleet = syncFleet;
        this.behavior = behavior;
    }

    @Override
    public void run(ApplicationArguments args) {
        syncFleet.sync(configuredFleet.robots());
        behavior.autoStart();
    }
}

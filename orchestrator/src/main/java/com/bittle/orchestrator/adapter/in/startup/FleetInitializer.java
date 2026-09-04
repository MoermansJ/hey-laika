package com.bittle.orchestrator.adapter.in.startup;

import com.bittle.orchestrator.application.usecase.AutoStartBehaviorLoopsUseCase;
import com.bittle.orchestrator.application.usecase.SyncFleetUseCase;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class FleetInitializer implements ApplicationRunner {

    private final SyncFleetUseCase syncFleet;
    private final AutoStartBehaviorLoopsUseCase autoStartLoops;

    public FleetInitializer(SyncFleetUseCase syncFleet,
                            AutoStartBehaviorLoopsUseCase autoStartLoops) {
        this.syncFleet = syncFleet;
        this.autoStartLoops = autoStartLoops;
    }

    @Override
    public void run(ApplicationArguments args) {
        syncFleet.execute();
        autoStartLoops.execute();
    }
}

package com.bittle.orchestrator.adapter.in.startup;

import com.bittle.orchestrator.application.usecase.AutoStartBehaviorLoopsUseCase;
import com.bittle.orchestrator.application.usecase.ResyncRobotModesUseCase;
import com.bittle.orchestrator.application.usecase.SyncFleetUseCase;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class FleetInitializer implements ApplicationRunner {

    private final SyncFleetUseCase syncFleet;
    private final AutoStartBehaviorLoopsUseCase autoStartLoops;
    private final ResyncRobotModesUseCase resyncModes;

    public FleetInitializer(SyncFleetUseCase syncFleet,
                            AutoStartBehaviorLoopsUseCase autoStartLoops,
                            ResyncRobotModesUseCase resyncModes) {
        this.syncFleet = syncFleet;
        this.autoStartLoops = autoStartLoops;
        this.resyncModes = resyncModes;
    }

    @Override
    public void run(ApplicationArguments args) {
        syncFleet.execute();
        autoStartLoops.execute();
        resyncModes.execute();
    }
}

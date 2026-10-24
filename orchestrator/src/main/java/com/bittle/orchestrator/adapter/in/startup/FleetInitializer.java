package com.bittle.orchestrator.adapter.in.startup;

import com.bittle.orchestrator.application.usecase.AutoStartBehaviorLoopsUseCase;
import com.bittle.orchestrator.application.usecase.ResyncRobotIntroductionsUseCase;
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
    private final ResyncRobotIntroductionsUseCase resyncIntroductions;

    public FleetInitializer(SyncFleetUseCase syncFleet,
                            AutoStartBehaviorLoopsUseCase autoStartLoops,
                            ResyncRobotModesUseCase resyncModes,
                            ResyncRobotIntroductionsUseCase resyncIntroductions) {
        this.syncFleet = syncFleet;
        this.autoStartLoops = autoStartLoops;
        this.resyncModes = resyncModes;
        this.resyncIntroductions = resyncIntroductions;
    }

    @Override
    public void run(ApplicationArguments args) {
        syncFleet.execute();
        autoStartLoops.execute();
        resyncModes.execute();
        // The adapter's introduction mirror is in-memory, so it needs restoring
        // after an adapter restart just as the mode does.
        resyncIntroductions.execute();
    }
}

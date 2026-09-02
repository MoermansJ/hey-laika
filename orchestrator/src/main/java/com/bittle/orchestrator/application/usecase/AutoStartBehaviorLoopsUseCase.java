package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.BehaviorSettings;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.application.service.FleetRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AutoStartBehaviorLoopsUseCase {

    private static final Logger log = LoggerFactory.getLogger(AutoStartBehaviorLoopsUseCase.class);

    private final FleetRegistry registry;
    private final BehaviorLoops loops;
    private final BehaviorSettings settings;

    public AutoStartBehaviorLoopsUseCase(FleetRegistry registry, BehaviorLoops loops,
                                         BehaviorSettings settings) {
        this.registry = registry;
        this.loops = loops;
        this.settings = settings;
    }

    public void execute() {
        if (!settings.autoStart()) {
            return;
        }
        registry.all().forEach(robot -> loops.loop(robot.id()).start());
        log.info("Auto-started {} behavior loop(s)", registry.all().size());
    }
}

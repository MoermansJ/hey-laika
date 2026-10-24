package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotIntroductionRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Pushes every stored introduction down at boot, mirroring
 * {@link ResyncRobotModesUseCase}. The adapter's mirror is in-memory, so this
 * is what restores it after an adapter restart.
 */
public class ResyncRobotIntroductionsUseCase {

    private static final Logger log =
            LoggerFactory.getLogger(ResyncRobotIntroductionsUseCase.class);

    private final Fleet fleet;
    private final RobotIntroductionRepositoryPort introductions;
    private final RobotAdapterPort adapter;

    public ResyncRobotIntroductionsUseCase(Fleet fleet,
                                           RobotIntroductionRepositoryPort introductions,
                                           RobotAdapterPort adapter) {
        this.fleet = fleet;
        this.introductions = introductions;
        this.adapter = adapter;
    }

    public void execute() {
        fleet.all().forEach(this::resync);
    }

    private void resync(Robot robot) {
        var stored = introductions.find(robot.id()).filter(RobotIntroduction::stored);
        if (stored.isEmpty()) {
            return;     // nothing written yet: the adapter keeps its compiled default
        }
        try {
            adapter.post(robot, "/conversation/introduction",
                    Map.of("introduction", stored.get().text()));
        } catch (RuntimeException e) {
            log.debug("Skipping introduction resync for {}: {}", robot.id(), e.getMessage());
        }
    }
}

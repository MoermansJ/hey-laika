package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotIntroductionRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SetRobotIntroductionUseCase {

    private static final Logger log = LoggerFactory.getLogger(SetRobotIntroductionUseCase.class);

    private final Fleet fleet;
    private final RobotIntroductionRepositoryPort introductions;
    private final RobotAdapterPort adapter;
    private final EventPublisherPort publisher;

    public SetRobotIntroductionUseCase(Fleet fleet, RobotIntroductionRepositoryPort introductions,
                                       RobotAdapterPort adapter, EventPublisherPort publisher) {
        this.fleet = fleet;
        this.introductions = introductions;
        this.adapter = adapter;
        this.publisher = publisher;
    }

    public RobotIntroduction execute(String robotId, String text, String updatedBy) {
        var robot = fleet.get(robotId);
        var record = RobotIntroduction.of(robot.id(), text, updatedBy);
        // Deliberately the other way round from SetRobotModeUseCase, which posts
        // to the adapter first so a failed push aborts the switch. Introduction
        // text has to stay editable while Laika is off, so it is persisted first
        // and pushed best-effort; ResyncRobotIntroductionsUseCase re-pushes at
        // boot, so a robot that was down still catches up.
        introductions.save(record);
        push(robot, record);
        publisher.publish("/topic/robot/" + robot.id() + "/introduction", record);
        return record;
    }

    private void push(Robot robot, RobotIntroduction introduction) {
        try {
            adapter.post(robot, "/conversation/introduction",
                    Map.of("introduction", introduction.text()));
        } catch (RuntimeException e) {
            log.info("Introduction saved but not pushed to {}: {}", robot.id(), e.getMessage());
        }
    }
}

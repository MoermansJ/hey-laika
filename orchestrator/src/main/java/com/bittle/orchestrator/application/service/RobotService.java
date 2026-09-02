package com.bittle.orchestrator.application.service;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.in.BehaviorUseCase;
import com.bittle.orchestrator.application.port.in.RobotOperationsUseCase;
import com.bittle.orchestrator.application.port.in.RobotPassthroughUseCase;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.ActivityLog;
import com.bittle.orchestrator.domain.robot.AnimationList;
import com.bittle.orchestrator.domain.robot.AnimationResult;
import com.bittle.orchestrator.domain.robot.AutonomousState;
import com.bittle.orchestrator.domain.robot.CommandResult;
import com.bittle.orchestrator.domain.robot.DisplayContent;
import com.bittle.orchestrator.domain.robot.ExecuteActionRequest;
import com.bittle.orchestrator.domain.robot.InteractionResult;
import com.bittle.orchestrator.domain.robot.RobotBehavior;
import com.bittle.orchestrator.domain.robot.RobotPersonality;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import com.bittle.orchestrator.domain.robot.ServoMoveRequest;
import com.bittle.orchestrator.domain.robot.ServoMoveResult;
import com.bittle.orchestrator.domain.robot.ServoState;
import java.util.Map;

/** Resolves the robot and proxies robot-scoped operations to its adapter. */
public class RobotService implements RobotOperationsUseCase, RobotPassthroughUseCase {

    private final FleetRegistry registry;
    private final RobotAdapterPort adapter;
    private final BehaviorUseCase behavior;

    public RobotService(FleetRegistry registry, RobotAdapterPort adapter, BehaviorUseCase behavior) {
        this.registry = registry;
        this.adapter = adapter;
        this.behavior = behavior;
    }

    @Override
    public RobotStatus status(String robotId) {
        return adapter.status(robot(robotId));
    }

    @Override
    public RobotPersonality personality(String robotId) {
        return adapter.personality(robot(robotId));
    }

    @Override
    public RobotBehavior nextBehavior(String robotId) {
        return adapter.nextBehavior(robot(robotId));
    }

    @Override
    public CommandResult command(String robotId, String command) {
        return adapter.command(robot(robotId), command);
    }

    @Override
    public InteractionResult interact(String robotId, String type) {
        return adapter.interact(robot(robotId), type);
    }

    @Override
    public AnimationList animations(String robotId) {
        return adapter.animations(robot(robotId));
    }

    @Override
    public AnimationResult executeAnimation(String robotId, String animation) {
        return adapter.executeAnimation(robot(robotId), animation);
    }

    @Override
    public AutonomousState startAutonomous(String robotId) {
        return adapter.startAutonomous(robot(robotId));
    }

    @Override
    public AutonomousState stopAutonomous(String robotId) {
        return adapter.stopAutonomous(robot(robotId));
    }

    @Override
    public AutonomousState autonomousStatus(String robotId) {
        return adapter.autonomousStatus(robot(robotId));
    }

    @Override
    public ActivityLog activity(String robotId) {
        return adapter.activity(robot(robotId));
    }

    @Override
    public DisplayContent display(String robotId) {
        return adapter.display(robot(robotId));
    }

    @Override
    public Map<String, Object> capabilities(String robotId) {
        return adapter.capabilities(robot(robotId));
    }

    @Override
    public ServoState servoState(String robotId) {
        return adapter.servoState(robot(robotId));
    }

    @Override
    public ServoMoveResult moveServos(String robotId, ServoMoveRequest request) {
        return adapter.moveServos(robot(robotId), request);
    }

    @Override
    public Map<String, Object> voiceDemo(String robotId, Map<String, Object> body) {
        return adapter.voiceDemo(robot(robotId), body);
    }

    @Override
    public Map<String, Object> voiceHealth(String robotId) {
        return adapter.voiceHealth(robot(robotId));
    }

    @Override
    public Map<String, Object> sound(String robotId, Map<String, Object> body) {
        return adapter.sound(robot(robotId), body);
    }

    /** The loop check comes first: it also resolves the robot, so 404 and 409 precede any adapter error. */
    @Override
    public ActionResult executeAction(String robotId, ExecuteActionRequest request) {
        if (behavior.isRunning(robotId)) {
            throw new BehaviorLoopRunningException();
        }
        return adapter.executeAction(robot(robotId), request);
    }

    @Override
    public Map<String, Object> get(String robotId, String path) {
        return adapter.get(robot(robotId), path);
    }

    @Override
    public Map<String, Object> post(String robotId, String path) {
        return adapter.post(robot(robotId), path);
    }

    @Override
    public Map<String, Object> post(String robotId, String path, Map<String, Object> body) {
        return adapter.post(robot(robotId), path, body);
    }

    private Robot robot(String robotId) {
        return registry.get(robotId);
    }
}

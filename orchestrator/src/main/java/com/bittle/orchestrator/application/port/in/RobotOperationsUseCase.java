package com.bittle.orchestrator.application.port.in;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
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

/**
 * Typed robot-scoped operations, each proxied to the robot's adapter. Every
 * method throws {@link RobotNotFoundException} for an unknown robot id.
 */
public interface RobotOperationsUseCase {

    RobotStatus status(String robotId);

    RobotPersonality personality(String robotId);

    RobotBehavior nextBehavior(String robotId);

    CommandResult command(String robotId, String command);

    InteractionResult interact(String robotId, String type);

    AnimationList animations(String robotId);

    AnimationResult executeAnimation(String robotId, String animation);

    AutonomousState startAutonomous(String robotId);

    AutonomousState stopAutonomous(String robotId);

    AutonomousState autonomousStatus(String robotId);

    ActivityLog activity(String robotId);

    DisplayContent display(String robotId);

    Map<String, Object> capabilities(String robotId);

    ServoState servoState(String robotId);

    ServoMoveResult moveServos(String robotId, ServoMoveRequest request);

    Map<String, Object> voiceDemo(String robotId, Map<String, Object> body);

    Map<String, Object> voiceHealth(String robotId);

    Map<String, Object> sound(String robotId, Map<String, Object> body);

    /**
     * Direct movement execution for the choreography builder.
     *
     * @throws BehaviorLoopRunningException while the behavior loop drives the robot
     */
    ActionResult executeAction(String robotId, ExecuteActionRequest request);
}

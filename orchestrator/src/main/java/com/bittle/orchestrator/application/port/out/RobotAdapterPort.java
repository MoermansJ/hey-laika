package com.bittle.orchestrator.application.port.out;

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

/**
 * The robot's adapter service, which implements all hardware/AI logic.
 * Implementations throw {@link AdapterUnavailableException} when the adapter
 * cannot be reached and {@link AdapterErrorException} when it answers with an
 * error status.
 */
public interface RobotAdapterPort {

    /** The adapter's service-level metrics snapshot (untyped passthrough). */
    Map<String, Object> metrics(Robot robot);

    RobotStatus status(Robot robot);

    RobotPersonality personality(Robot robot);

    RobotBehavior nextBehavior(Robot robot);

    CommandResult command(Robot robot, String command);

    InteractionResult interact(Robot robot, String type);

    AnimationList animations(Robot robot);

    AnimationResult executeAnimation(Robot robot, String animation);

    AutonomousState startAutonomous(Robot robot);

    AutonomousState stopAutonomous(Robot robot);

    AutonomousState autonomousStatus(Robot robot);

    ActivityLog activity(Robot robot);

    ActionResult executeAction(Robot robot, ExecuteActionRequest request);

    DisplayContent display(Robot robot);

    /** The adapter's capability schema, untyped so new capability kinds need no release here. */
    Map<String, Object> capabilities(Robot robot);

    ServoState servoState(Robot robot);

    ServoMoveResult moveServos(Robot robot, ServoMoveRequest request);

    Map<String, Object> voiceDemo(Robot robot, Map<String, Object> body);

    Map<String, Object> voiceHealth(Robot robot);

    Map<String, Object> sound(Robot robot, Map<String, Object> body);

    // ---- Untyped passthrough; path is relative to the adapter's robot root ----

    Map<String, Object> get(Robot robot, String path);

    Map<String, Object> post(Robot robot, String path);

    Map<String, Object> post(Robot robot, String path, Map<String, Object> body);
}

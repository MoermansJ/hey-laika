package com.bittle.orchestrator.agent;

import com.bittle.orchestrator.client.PythonServiceClient;
import com.bittle.orchestrator.config.RobotsProperties.RobotDefinition;
import com.bittle.orchestrator.dto.Dtos.ActivityLog;
import com.bittle.orchestrator.dto.Dtos.AnimationList;
import com.bittle.orchestrator.dto.Dtos.AnimationResult;
import com.bittle.orchestrator.dto.Dtos.AutonomousState;
import com.bittle.orchestrator.dto.Dtos.CommandResult;
import com.bittle.orchestrator.dto.Dtos.DisplayContent;
import com.bittle.orchestrator.dto.Dtos.InteractionResult;
import com.bittle.orchestrator.dto.Dtos.RobotBehavior;
import com.bittle.orchestrator.dto.Dtos.RobotInfo;
import com.bittle.orchestrator.dto.Dtos.RobotPersonality;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * One robot instance on the management platform. All hardware/AI concerns are
 * delegated to the robot's Python adapter service — this class only knows the
 * robot's identity and where its adapter lives.
 */
public class RobotAgent {

    private static final Logger log = LoggerFactory.getLogger(RobotAgent.class);

    private final RobotDefinition definition;
    private final PythonServiceClient client;

    public RobotAgent(RobotDefinition definition, PythonServiceClient client) {
        this.definition = definition;
        this.client = client;
    }

    public String id() {
        return definition.id();
    }

    public RobotInfo info() {
        return new RobotInfo(definition.id(), definition.name(), definition.type(),
                definition.serviceUrl(), true);
    }

    public RobotStatus status() {
        return client.status(definition.serviceUrl(), definition.id());
    }

    /** Status that never throws — used for fleet-wide overviews. */
    public RobotStatus statusOrUnreachable() {
        try {
            return status();
        } catch (RuntimeException e) {
            log.warn("Robot {} unreachable: {}", definition.id(), e.getMessage());
            return RobotStatus.unreachable(definition.id());
        }
    }

    public RobotPersonality personality() {
        return client.personality(definition.serviceUrl(), definition.id());
    }

    public RobotBehavior nextBehavior() {
        return client.nextBehavior(definition.serviceUrl(), definition.id());
    }

    public CommandResult command(String command) {
        return client.command(definition.serviceUrl(), definition.id(), command);
    }

    public InteractionResult interact(String type) {
        return client.interact(definition.serviceUrl(), definition.id(), type);
    }

    public AnimationList animations() {
        return client.animations(definition.serviceUrl(), definition.id());
    }

    public AnimationResult executeAnimation(String animation) {
        return client.executeAnimation(definition.serviceUrl(), definition.id(), animation);
    }

    public AutonomousState startAutonomous() {
        return client.startAutonomous(definition.serviceUrl(), definition.id());
    }

    public AutonomousState stopAutonomous() {
        return client.stopAutonomous(definition.serviceUrl(), definition.id());
    }

    public AutonomousState autonomousStatus() {
        return client.autonomousStatus(definition.serviceUrl(), definition.id());
    }

    public ActivityLog activity() {
        return client.activity(definition.serviceUrl(), definition.id());
    }

    public DisplayContent display() {
        return client.display(definition.serviceUrl(), definition.id());
    }
}

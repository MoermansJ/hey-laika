package com.bittle.orchestrator.dto;

import java.util.List;
import java.util.Map;

/**
 * Response shapes exchanged with the Python adapter services and served to
 * the UI. Field names mirror the adapters' camelCase JSON exactly.
 */
public final class Dtos {

    private Dtos() {
    }

    public record RobotStatus(String robotId, boolean connected, String mode,
                              String lastCommand, Integer commandsSent,
                              Boolean autonomous, String mood, Double battery,
                              String signal, Long uptimeSeconds) {

        public static RobotStatus unreachable(String robotId) {
            return new RobotStatus(robotId, false, null, null, null, null, null,
                    null, null, null);
        }
    }

    public record RobotPersonality(String robotId, double energy, double happiness,
                                   double boredom, double curiosity, String mood) {
    }

    public record RobotBehavior(String robotId, String behavior, String reason, String source) {
    }

    public record CommandRequest(String command) {
    }

    public record CommandResult(String robotId, String command, boolean success) {
    }

    public record InteractionResult(String robotId, String interaction,
                                    Map<String, Object> personality) {
    }

    public record AnimationList(String robotId, List<Animation> animations) {

        public record Animation(String name, String description, int frames) {
        }
    }

    public record AnimationResult(String robotId, String animation, boolean success) {
    }

    public record AutonomousState(String robotId, boolean running, Boolean changed,
                                  Integer intervalSeconds) {
    }

    public record ActivityLog(String robotId, List<ActivityEntry> activity) {

        public record ActivityEntry(String kind, String message, String at) {
        }
    }

    public record DisplayContent(String robotId, String type, String value, String updatedAt) {
    }

    public record RobotInfo(String robotId, String name, String type, String serviceUrl,
                            boolean active) {
    }

    public record FleetStats(int totalRobots, long connectedRobots, long autonomousRobots,
                             long timestamp) {
    }
}

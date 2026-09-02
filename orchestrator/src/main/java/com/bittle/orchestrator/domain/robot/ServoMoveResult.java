package com.bittle.orchestrator.domain.robot;

import java.util.List;

public record ServoMoveResult(String robotId, boolean success, Boolean clamped,
                              String message, List<ServoJoint> movedJoints) {
}

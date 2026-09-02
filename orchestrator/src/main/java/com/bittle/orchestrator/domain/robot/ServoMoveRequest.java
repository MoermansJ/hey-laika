package com.bittle.orchestrator.domain.robot;

import java.util.List;

public record ServoMoveRequest(List<ServoJoint> joints) {
}

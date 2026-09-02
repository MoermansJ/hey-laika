package com.bittle.orchestrator.domain.robot;

import java.util.List;

public record ServoState(String robotId, boolean success, String timestamp,
                         List<ServoJoint> joints) {
}

package com.bittle.orchestrator.application.port.in;

import java.util.Map;

/**
 * Untyped passthrough to the robot's adapter for host-side features the
 * orchestrator only relays (lifecycle, power, polling, senses, leash,
 * behavior framework). {@code path} is relative to the adapter's robot root.
 */
public interface RobotPassthroughUseCase {

    Map<String, Object> get(String robotId, String path);

    Map<String, Object> post(String robotId, String path);

    Map<String, Object> post(String robotId, String path, Map<String, Object> body);
}

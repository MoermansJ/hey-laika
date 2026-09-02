package com.bittle.orchestrator.infrastructure.config;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Robot instances managed by the platform, from application.yml / environment.
 * Each robot is backed by one Python adapter service reachable at serviceUrl.
 */
@ConfigurationProperties(prefix = "bittle")
public record RobotsProperties(List<RobotDefinition> robots) {

    public record RobotDefinition(String id, String name, String type, String serviceUrl) {
    }
}

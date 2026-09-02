package com.bittle.orchestrator.infrastructure.config;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "bittle")
public record RobotsProperties(List<RobotDefinition> robots) {

    public record RobotDefinition(String id, String name, String type, String serviceUrl) {
    }
}

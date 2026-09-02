package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.ListRobotsUseCase;
import java.time.Instant;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    private final ListRobotsUseCase listRobots;

    public HealthController(ListRobotsUseCase listRobots) {
        this.listRobots = listRobots;
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of(
                "status", "healthy",
                "service", "bittle-orchestrator",
                "fleetSize", listRobots.execute().size(),
                "timestamp", Instant.now().toString());
    }
}

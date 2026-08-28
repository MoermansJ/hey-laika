package com.bittle.orchestrator.controller;

import com.bittle.orchestrator.fleet.FleetManager;
import java.time.Instant;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    private final FleetManager fleetManager;

    public HealthController(FleetManager fleetManager) {
        this.fleetManager = fleetManager;
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of(
                "status", "healthy",
                "service", "bittle-orchestrator",
                "fleetSize", fleetManager.all().size(),
                "timestamp", Instant.now().toString());
    }
}

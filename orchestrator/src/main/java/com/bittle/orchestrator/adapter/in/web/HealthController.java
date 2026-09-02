package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.port.in.FleetUseCase;
import java.time.Instant;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    private final FleetUseCase fleet;

    public HealthController(FleetUseCase fleet) {
        this.fleet = fleet;
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of(
                "status", "healthy",
                "service", "bittle-orchestrator",
                "fleetSize", fleet.robots().size(),
                "timestamp", Instant.now().toString());
    }
}

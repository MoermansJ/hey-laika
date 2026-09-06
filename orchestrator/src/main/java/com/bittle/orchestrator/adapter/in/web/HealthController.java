package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetFleetHealthUseCase;
import com.bittle.orchestrator.domain.fleet.FleetHealth;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Health", description = "Aggregated fleet health")
public class HealthController {

    private final GetFleetHealthUseCase getFleetHealth;

    public HealthController(GetFleetHealthUseCase getFleetHealth) {
        this.getFleetHealth = getFleetHealth;
    }

    @Operation(summary = "Aggregated health",
            description = "healthy, degraded when some adapters are unreachable, down when none are.")
    @GetMapping("/api/health")
    public FleetHealth health() {
        return getFleetHealth.execute();
    }
}

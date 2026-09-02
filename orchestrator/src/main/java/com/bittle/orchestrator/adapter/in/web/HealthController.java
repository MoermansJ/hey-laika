package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetFleetHealthUseCase;
import com.bittle.orchestrator.domain.fleet.FleetHealth;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    private final GetFleetHealthUseCase getFleetHealth;

    public HealthController(GetFleetHealthUseCase getFleetHealth) {
        this.getFleetHealth = getFleetHealth;
    }

    @GetMapping("/api/health")
    public FleetHealth health() {
        return getFleetHealth.execute();
    }
}

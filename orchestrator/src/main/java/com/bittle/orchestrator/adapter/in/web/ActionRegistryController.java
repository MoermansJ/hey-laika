package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.usecase.GetActionRegistryEntryUseCase;
import com.bittle.orchestrator.application.usecase.GetActionRegistryUseCase;
import com.bittle.orchestrator.domain.behavior.ActionRegistryEntry;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "Actions", description = "Read-only catalog of robot actions and their voice/GUI metadata")
@RequestMapping("/api/actions")
public class ActionRegistryController {

    private final GetActionRegistryUseCase getRegistry;
    private final GetActionRegistryEntryUseCase getRegistryEntry;

    public ActionRegistryController(GetActionRegistryUseCase getRegistry,
                                    GetActionRegistryEntryUseCase getRegistryEntry) {
        this.getRegistry = getRegistry;
        this.getRegistryEntry = getRegistryEntry;
    }

    @Operation(summary = "List the action registry",
            description = "Every known action with its aliases, description and tags.")
    @GetMapping
    public Map<String, List<ActionRegistryEntry>> actions() {
        return Map.of("actions", getRegistry.execute());
    }

    @Operation(summary = "Get a single action registry entry",
            description = "404 action_not_found for an unknown action name.")
    @GetMapping("/{actionName}")
    public ActionRegistryEntry action(@PathVariable String actionName) {
        return getRegistryEntry.execute(actionName);
    }
}

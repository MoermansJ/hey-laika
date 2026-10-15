package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.ActionCatalog;
import com.bittle.orchestrator.domain.behavior.ActionRegistryEntry;
import java.util.Arrays;
import java.util.List;

public class GetActionRegistryUseCase {

    public List<ActionRegistryEntry> execute() {
        return Arrays.stream(Action.values())
                .map(action -> ActionRegistryEntry.of(action, ActionCatalog.metadataFor(action)))
                .toList();
    }
}

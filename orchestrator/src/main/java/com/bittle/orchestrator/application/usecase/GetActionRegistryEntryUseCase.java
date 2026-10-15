package com.bittle.orchestrator.application.usecase;

import com.bittle.orchestrator.domain.behavior.Action;
import com.bittle.orchestrator.domain.behavior.ActionCatalog;
import com.bittle.orchestrator.domain.behavior.ActionNotFoundException;
import com.bittle.orchestrator.domain.behavior.ActionRegistryEntry;

public class GetActionRegistryEntryUseCase {

    public ActionRegistryEntry execute(String actionName) {
        for (Action action : Action.values()) {
            if (action.actionId().equalsIgnoreCase(actionName)) {
                return ActionRegistryEntry.of(action, ActionCatalog.metadataFor(action));
            }
        }
        throw new ActionNotFoundException(actionName);
    }
}

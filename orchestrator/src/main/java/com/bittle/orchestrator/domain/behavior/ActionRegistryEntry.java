package com.bittle.orchestrator.domain.behavior;

import java.util.List;

public record ActionRegistryEntry(String actionName, List<String> aliases, String description,
                                  List<String> tags) {

    public static ActionRegistryEntry of(Action action, ActionMetadata metadata) {
        return new ActionRegistryEntry(action.actionId(), metadata.aliases(),
                metadata.description(), metadata.tags());
    }
}

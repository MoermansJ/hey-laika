package com.bittle.orchestrator.domain.behavior;

import java.util.List;

public record ActionMetadata(List<String> aliases, String description, List<String> tags) {
}

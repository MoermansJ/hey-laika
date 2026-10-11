package com.bittle.orchestrator.domain.behavior;

import java.util.Objects;

/**
 * One tool (named behavior) the agent may call (AGENT_TOOL_COMPOSITION_DESIGN.md §3.3).
 *
 * @param name        behavior name submitted to the arbiter
 * @param description what the tool does, for the agent's prompt
 * @param category    "postural" | "locomotive" | "vocal"
 */
public record ToolDescriptor(String name, String description, String category) {

    public ToolDescriptor {
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(description, "description");
        Objects.requireNonNull(category, "category");
    }
}

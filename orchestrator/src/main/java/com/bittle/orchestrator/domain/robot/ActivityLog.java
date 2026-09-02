package com.bittle.orchestrator.domain.robot;

import java.util.List;

public record ActivityLog(String robotId, List<ActivityEntry> activity) {

    public record ActivityEntry(String kind, String message, String at) {
    }
}

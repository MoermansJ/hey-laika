package com.bittle.orchestrator.domain.robot;

import java.util.List;

public record AnimationList(String robotId, List<Animation> animations) {

    public record Animation(String name, String description, int frames) {
    }
}

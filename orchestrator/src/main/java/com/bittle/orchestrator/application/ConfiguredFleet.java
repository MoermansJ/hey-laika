package com.bittle.orchestrator.application;

import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.List;

/** The robots this platform manages, as declared in configuration. */
public record ConfiguredFleet(List<Robot> robots) {
}

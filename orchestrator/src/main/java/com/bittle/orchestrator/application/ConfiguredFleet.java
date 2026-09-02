package com.bittle.orchestrator.application;

import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.List;

public record ConfiguredFleet(List<Robot> robots) {
}

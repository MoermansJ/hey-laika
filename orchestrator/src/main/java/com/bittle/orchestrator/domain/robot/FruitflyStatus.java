package com.bittle.orchestrator.domain.robot;

import java.util.Map;

/**
 * fruitfly_drive.py's status() (observability only): the open-loop
 * locomotor decode (lastState/lastSignals) plus, when the giant-fiber
 * sidecar is wired in (gfEnabled), its live signal -- gfRateHz/gfSpikes are
 * what the camera is driving the brain to right now, lastGfAt/lastEscapeAt
 * are epoch-seconds timestamps (null if nothing has fired yet) the GUI's
 * Fruitfly card turns into "x s ago".
 */
public record FruitflyStatus(String robotId, String lastState, Map<String, Object> lastSignals,
                             boolean gfEnabled, Double gfRateHz, Integer gfSpikes,
                             Double lastGfAt, Double lastEscapeAt) {
}

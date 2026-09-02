package com.bittle.orchestrator.application.port.in;

import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.List;

/**
 * Syncs the configured robot list into the fleet database and registers each
 * robot as live. Robots that disappear from configuration are kept in the
 * database (history) but marked inactive and not registered.
 */
public interface SyncFleetUseCase {

    void sync(List<Robot> configured);
}

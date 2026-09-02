package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.Collection;
import java.util.List;

/** Durable fleet metadata (which robots exist, and whether they are still configured). */
public interface FleetRepositoryPort {

    /** Inserts or updates the robot's metadata and marks it active. */
    void upsertActive(Robot robot);

    /**
     * Marks every stored robot whose id is not in {@code ids} inactive.
     *
     * @return the ids that were marked inactive
     */
    List<String> deactivateAllExcept(Collection<String> ids);
}

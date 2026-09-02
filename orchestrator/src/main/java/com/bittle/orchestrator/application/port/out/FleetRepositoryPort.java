package com.bittle.orchestrator.application.port.out;

import com.bittle.orchestrator.domain.fleet.Robot;
import java.util.Collection;
import java.util.List;

public interface FleetRepositoryPort {

    void upsertActive(Robot robot);

    List<String> deactivateAllExcept(Collection<String> ids);
}

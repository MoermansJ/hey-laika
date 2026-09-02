package com.bittle.orchestrator.application.port.in;

import com.bittle.orchestrator.domain.fleet.FleetStats;
import com.bittle.orchestrator.domain.fleet.RobotInfo;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.List;
import java.util.Map;

/** Fleet-wide queries and bulk operations. */
public interface FleetUseCase {

    List<RobotInfo> robots();

    /** Status per robot id; unreachable adapters yield {@link RobotStatus#unreachable}. */
    Map<String, RobotStatus> fleetStatus();

    FleetStats stats();

    /** Per robot id: whether the adapter reports autonomous mode running afterwards. */
    Map<String, Boolean> startAllAutonomous();

    /** Per robot id: whether the adapter reports autonomous mode stopped afterwards. */
    Map<String, Boolean> stopAllAutonomous();
}

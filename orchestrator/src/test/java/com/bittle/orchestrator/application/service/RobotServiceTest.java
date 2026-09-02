package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.in.BehaviorUseCase;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.ExecuteActionRequest;
import org.junit.jupiter.api.Test;

class RobotServiceTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");
    private static final ExecuteActionRequest SIT = new ExecuteActionRequest("sit_down", 1500, 1);

    private final FleetRegistry registry = new FleetRegistry();
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final BehaviorUseCase behavior = mock(BehaviorUseCase.class);
    private final RobotService service = new RobotService(registry, adapter, behavior);

    @Test
    void givenLoopStopped_whenActionExecuted_thenItIsProxiedToTheAdapter() {
        registry.register(LAIKA);
        when(behavior.isRunning("bittle-1")).thenReturn(false);
        var executed = new ActionResult("bittle-1", "sit_down", true, 1500L, "executed");
        when(adapter.executeAction(LAIKA, SIT)).thenReturn(executed);

        var result = service.executeAction("bittle-1", SIT);

        assertThat(result).isSameAs(executed);
    }

    @Test
    void givenLoopRunning_whenActionExecuted_thenItIsRefusedBeforeReachingTheAdapter() {
        registry.register(LAIKA);
        when(behavior.isRunning("bittle-1")).thenReturn(true);

        assertThatThrownBy(() -> service.executeAction("bittle-1", SIT))
                .isInstanceOf(BehaviorLoopRunningException.class);
        verifyNoInteractions(adapter);
    }

    @Test
    void givenUnknownRobot_whenStatusRequested_thenRobotNotFoundIsThrown() {
        assertThatThrownBy(() -> service.status("ghost"))
                .isInstanceOf(RobotNotFoundException.class);
        verifyNoInteractions(adapter);
    }

    @Test
    void givenRegisteredRobot_whenPassthroughGet_thenPathIsRelayedToTheAdapter() {
        registry.register(LAIKA);
        when(adapter.get(LAIKA, "/power")).thenReturn(java.util.Map.of("sessions", 2));

        var result = service.get("bittle-1", "/power");

        assertThat(result).containsEntry("sessions", 2);
    }
}

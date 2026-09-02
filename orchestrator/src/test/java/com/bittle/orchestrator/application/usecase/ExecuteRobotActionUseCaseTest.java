package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.application.service.RobotBehaviorLoop;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import com.bittle.orchestrator.domain.robot.ActionResult;
import com.bittle.orchestrator.domain.robot.ExecuteActionRequest;
import org.junit.jupiter.api.Test;

class ExecuteRobotActionUseCaseTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");
    private static final ExecuteActionRequest SIT = new ExecuteActionRequest("sit_down", 1500, 1);

    private final FleetRegistry registry = new FleetRegistry();
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final BehaviorLoops loops = mock(BehaviorLoops.class);
    private final RobotBehaviorLoop loop = mock(RobotBehaviorLoop.class);
    private final ExecuteRobotActionUseCase useCase =
            new ExecuteRobotActionUseCase(registry, adapter, loops);

    @Test
    void givenLoopStopped_whenExecuted_thenTheActionIsProxiedToTheAdapter() {
        registry.register(LAIKA);
        when(loops.loop("bittle-1")).thenReturn(loop);
        when(loop.isRunning()).thenReturn(false);
        var executed = new ActionResult("bittle-1", "sit_down", true, 1500L, "executed");
        when(adapter.executeAction(LAIKA, SIT)).thenReturn(executed);

        var result = useCase.execute("bittle-1", SIT);

        assertThat(result).isSameAs(executed);
    }

    @Test
    void givenLoopRunning_whenExecuted_thenItIsRefusedBeforeReachingTheAdapter() {
        registry.register(LAIKA);
        when(loops.loop("bittle-1")).thenReturn(loop);
        when(loop.isRunning()).thenReturn(true);

        assertThatThrownBy(() -> useCase.execute("bittle-1", SIT))
                .isInstanceOf(BehaviorLoopRunningException.class);
        verifyNoInteractions(adapter);
    }

    @Test
    void givenUnknownRobot_whenExecuted_thenRobotNotFoundIsThrownBeforeReachingTheAdapter() {
        when(loops.loop("ghost")).thenThrow(new RobotNotFoundException("ghost"));

        assertThatThrownBy(() -> useCase.execute("ghost", SIT))
                .isInstanceOf(RobotNotFoundException.class);
        verifyNoInteractions(adapter);
    }
}

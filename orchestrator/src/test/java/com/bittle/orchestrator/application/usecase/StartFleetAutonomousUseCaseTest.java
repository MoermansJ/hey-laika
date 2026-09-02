package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.service.FleetRegistry;
import com.bittle.orchestrator.application.service.FleetSweep;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.AutonomousState;
import org.junit.jupiter.api.Test;

class StartFleetAutonomousUseCaseTest {

    private static final Robot UP = new Robot("up", "Up", "mock", "http://up");
    private static final Robot DOWN = new Robot("down", "Down", "mock", "http://down");

    private final FleetRegistry registry = new FleetRegistry();
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final StartFleetAutonomousUseCase useCase =
            new StartFleetAutonomousUseCase(new FleetSweep(registry), adapter);

    @Test
    void givenOneStartingAndOneFailingAdapter_whenExecuted_thenEachRobotReportsItsOutcome() {
        registry.register(UP);
        registry.register(DOWN);
        when(adapter.startAutonomous(UP)).thenReturn(new AutonomousState("up", true, true, 5));
        when(adapter.startAutonomous(DOWN)).thenThrow(new IllegalStateException("boom"));

        var result = useCase.execute();

        assertThat(result)
                .containsEntry("up", true)
                .containsEntry("down", false);
    }
}

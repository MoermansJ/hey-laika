package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.application.service.BehaviorLoops;
import com.bittle.orchestrator.application.service.RobotBehaviorLoop;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class SetRobotModeUseCaseTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");

    private final Fleet fleet = new Fleet(List.of(LAIKA));
    private final RobotModeRepositoryPort modes = mock(RobotModeRepositoryPort.class);
    private final BehaviorLoops loops = mock(BehaviorLoops.class);
    private final RobotBehaviorLoop loop = mock(RobotBehaviorLoop.class);
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final EventPublisherPort publisher = mock(EventPublisherPort.class);
    private final SetRobotModeUseCase useCase =
            new SetRobotModeUseCase(fleet, modes, loops, adapter, publisher);

    @Test
    void givenStationaryTarget_whenExecuted_thenTheLoopIsNotStartedAndTheAdapterAndStoreAreUpdated() {
        when(loops.loop("bittle-1")).thenReturn(loop);

        var result = useCase.execute("bittle-1", OperatingMode.STATIONARY, "gui");

        verify(loop).stop();
        verify(loop, never()).start();
        verify(adapter).post(LAIKA, "/mode", Map.of("mode", "stationary"));
        verify(modes).save(result);
        verify(publisher).publish("/topic/robot/bittle-1/mode", result);
        assertThat(result.mode()).isEqualTo(OperatingMode.STATIONARY);
        assertThat(result.changedBy()).isEqualTo("gui");
    }

    @Test
    void givenRoamingTarget_whenExecuted_thenTheLoopIsStoppedInsteadOfStarted() {
        when(loops.loop("bittle-1")).thenReturn(loop);

        var result = useCase.execute("bittle-1", OperatingMode.ROAMING, "gui");

        verify(loop).stop();
        verify(loop, never()).start();
        verify(adapter).post(LAIKA, "/mode", Map.of("mode", "roaming"));
        assertThat(result.mode()).isEqualTo(OperatingMode.ROAMING);
    }

    @Test
    void givenFruitflyTarget_whenExecuted_thenTheLoopIsStoppedAndTheAdapterToldFruitfly() {
        when(loops.loop("bittle-1")).thenReturn(loop);

        var result = useCase.execute("bittle-1", OperatingMode.FRUITFLY, "gui");

        verify(loop).stop();
        verify(adapter).post(LAIKA, "/mode", Map.of("mode", "fruitfly"));
        assertThat(result.mode()).isEqualTo(OperatingMode.FRUITFLY);
    }

    @Test
    void givenPhoneTarget_whenExecuted_thenTheLoopIsStoppedAndTheAdapterToldPhone() {
        when(loops.loop("bittle-1")).thenReturn(loop);

        var result = useCase.execute("bittle-1", OperatingMode.PHONE, "gui");

        verify(loop).stop();
        verify(adapter).post(LAIKA, "/mode", Map.of("mode", "phone"));
        assertThat(result.mode()).isEqualTo(OperatingMode.PHONE);
    }

    @Test
    void givenUnknownRobot_whenExecuted_thenRobotNotFoundIsThrownWithoutTouchingAnything() {
        assertThatThrownBy(() -> useCase.execute("ghost", OperatingMode.STATIONARY, "gui"))
                .isInstanceOf(RobotNotFoundException.class);
        verifyNoInteractions(adapter, modes, publisher, loops);
    }
}

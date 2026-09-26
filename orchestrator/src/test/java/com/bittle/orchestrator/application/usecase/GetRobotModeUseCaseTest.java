package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class GetRobotModeUseCaseTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");

    private final Fleet fleet = new Fleet(List.of(LAIKA));
    private final RobotModeRepositoryPort modes = mock(RobotModeRepositoryPort.class);
    private final GetRobotModeUseCase useCase = new GetRobotModeUseCase(fleet, modes);

    @Test
    void givenNoStoredMode_whenExecuted_thenTheDefaultStationaryModeIsReturned() {
        when(modes.find("bittle-1")).thenReturn(Optional.empty());

        var result = useCase.execute("bittle-1");

        assertThat(result.mode()).isEqualTo(OperatingMode.STATIONARY);
    }

    @Test
    void givenAStoredMode_whenExecuted_thenItIsReturnedAsIs() {
        var stored = new RobotMode("bittle-1", OperatingMode.ROAMING, Instant.now(), "gui");
        when(modes.find("bittle-1")).thenReturn(Optional.of(stored));

        var result = useCase.execute("bittle-1");

        assertThat(result).isSameAs(stored);
    }

    @Test
    void givenUnknownRobot_whenExecuted_thenRobotNotFoundIsThrownWithoutTouchingTheStore() {
        assertThatThrownBy(() -> useCase.execute("ghost"))
                .isInstanceOf(RobotNotFoundException.class);
        verifyNoInteractions(modes);
    }
}

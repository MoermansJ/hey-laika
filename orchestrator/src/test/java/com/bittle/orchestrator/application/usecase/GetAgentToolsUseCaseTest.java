package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.RobotModeRepositoryPort;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.RobotMode;
import com.bittle.orchestrator.domain.behavior.ToolDescriptor;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class GetAgentToolsUseCaseTest {

    private final RobotModeRepositoryPort modes = mock(RobotModeRepositoryPort.class);
    private final GetAgentToolsUseCase useCase = new GetAgentToolsUseCase(
            new Fleet(List.of(new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika"))),
            modes);

    @Test
    void givenRoamingRobot_whenToolsRequested_thenWalkingToolsAreIncluded() {
        when(modes.find("bittle-1")).thenReturn(Optional.of(
                new RobotMode("bittle-1", OperatingMode.ROAMING, Instant.EPOCH, "gui")));

        assertThat(useCase.execute("bittle-1")).extracting(ToolDescriptor::name)
                .contains("move_forward");
    }

    @Test
    void givenNoStoredMode_whenToolsRequested_thenStationaryDefaultApplies() {
        when(modes.find("bittle-1")).thenReturn(Optional.empty());

        assertThat(useCase.execute("bittle-1")).extracting(ToolDescriptor::name)
                .doesNotContain("move_forward").contains("look_upward");
    }

    @Test
    void givenFruitflyRobot_whenToolsRequested_thenNone() {
        when(modes.find("bittle-1")).thenReturn(Optional.of(
                new RobotMode("bittle-1", OperatingMode.FRUITFLY, Instant.EPOCH, "gui")));

        assertThat(useCase.execute("bittle-1")).isEmpty();
    }

    @Test
    void givenUnknownRobot_whenToolsRequested_thenNotFound() {
        assertThatThrownBy(() -> useCase.execute("ghost"))
                .isInstanceOf(RobotNotFoundException.class);
    }
}

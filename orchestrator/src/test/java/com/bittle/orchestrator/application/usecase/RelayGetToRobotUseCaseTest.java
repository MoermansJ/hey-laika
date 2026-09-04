package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class RelayGetToRobotUseCaseTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");

    private final Fleet fleet = new Fleet(List.of(LAIKA));
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final RelayGetToRobotUseCase useCase = new RelayGetToRobotUseCase(fleet, adapter);

    @Test
    void givenRegisteredRobot_whenExecuted_thenThePathIsRelayedToTheAdapter() {
        when(adapter.get(LAIKA, "/power")).thenReturn(Map.of("sessions", 2));

        var result = useCase.execute("bittle-1", "/power");

        assertThat(result).containsEntry("sessions", 2);
    }

    @Test
    void givenUnknownRobot_whenExecuted_thenRobotNotFoundIsThrownWithoutTouchingTheAdapter() {
        assertThatThrownBy(() -> useCase.execute("ghost", "/power"))
                .isInstanceOf(RobotNotFoundException.class);
        verifyNoInteractions(adapter);
    }
}

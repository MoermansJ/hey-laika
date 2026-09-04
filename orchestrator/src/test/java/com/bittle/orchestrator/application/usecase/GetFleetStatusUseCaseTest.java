package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.RobotStatus;
import java.util.List;
import org.junit.jupiter.api.Test;

class GetFleetStatusUseCaseTest {

    private static final Robot UP = new Robot("up", "Up", "mock", "http://up");
    private static final Robot DOWN = new Robot("down", "Down", "mock", "http://down");
    private static final RobotStatus UP_STATUS = new RobotStatus("up", true, "mock", null, 3,
            true, "happy", 90.0, "strong", 60L, 1000.0);

    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);

    @Test
    void givenEmptyFleet_whenExecuted_thenResultIsEmpty() {
        assertThat(useCase().execute()).isEmpty();
    }

    @Test
    void givenReachableRobot_whenExecuted_thenAdapterStatusIsReturned() {
        when(adapter.status(UP)).thenReturn(UP_STATUS);

        var statuses = useCase(UP).execute();

        assertThat(statuses).containsEntry("up", UP_STATUS);
    }

    @Test
    void givenUnreachableRobot_whenExecuted_thenItIsReportedUnreachableInsteadOfFailing() {
        when(adapter.status(UP)).thenReturn(UP_STATUS);
        when(adapter.status(DOWN)).thenThrow(new AdapterUnavailableException("http://down", null));

        var statuses = useCase(UP, DOWN).execute();

        assertThat(statuses)
                .containsEntry("up", UP_STATUS)
                .containsEntry("down", RobotStatus.unreachable("down"));
    }

    private GetFleetStatusUseCase useCase(Robot... robots) {
        return new GetFleetStatusUseCase(new Fleet(List.of(robots)), adapter);
    }
}

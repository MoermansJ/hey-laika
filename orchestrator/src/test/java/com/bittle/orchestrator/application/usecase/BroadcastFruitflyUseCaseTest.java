package com.bittle.orchestrator.application.usecase;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.FruitflyStatus;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class BroadcastFruitflyUseCaseTest {

    private static final Robot ONE = new Robot("bittle-1", "One", "mock", "http://one");
    private static final Robot TWO = new Robot("bittle-2", "Two", "mock", "http://two");

    private final Fleet fleet = new Fleet(List.of(ONE, TWO));
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final EventPublisherPort publisher = mock(EventPublisherPort.class);
    private final BroadcastFruitflyUseCase useCase =
            new BroadcastFruitflyUseCase(fleet, adapter, publisher);

    @Test
    void givenOneUnreachableRobot_whenExecuted_thenTheOtherRobotIsStillPublished() {
        when(adapter.fruitflyStatus(ONE))
                .thenReturn(new FruitflyStatus("bittle-1", "FORWARD", Map.of("forward", 0.9)));
        when(adapter.fruitflyStatus(TWO)).thenThrow(new AdapterUnavailableException("http://two", null));

        useCase.execute();

        verify(publisher).publish(eq("/topic/robot/bittle-1/fruitfly"), any());
        verify(publisher, never()).publish(eq("/topic/robot/bittle-2/fruitfly"), any());
    }
}

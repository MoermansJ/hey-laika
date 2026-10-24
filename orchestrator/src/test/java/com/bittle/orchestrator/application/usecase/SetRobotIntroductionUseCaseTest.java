package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.EventPublisherPort;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotIntroductionRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class SetRobotIntroductionUseCaseTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");

    private final Fleet fleet = new Fleet(List.of(LAIKA));
    private final RobotIntroductionRepositoryPort introductions =
            mock(RobotIntroductionRepositoryPort.class);
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final EventPublisherPort publisher = mock(EventPublisherPort.class);
    private final SetRobotIntroductionUseCase useCase =
            new SetRobotIntroductionUseCase(fleet, introductions, adapter, publisher);

    @Test
    void givenText_whenExecuted_thenItIsStoredPushedAndBroadcast() {
        var result = useCase.execute("bittle-1", "  I am Laika.  ", "gui");

        assertThat(result.text()).isEqualTo("I am Laika.");       // stripped
        assertThat(result.updatedBy()).isEqualTo("gui");
        verify(introductions).save(result);
        verify(adapter).post(LAIKA, "/conversation/introduction",
                Map.of("introduction", "I am Laika."));
        verify(publisher).publish("/topic/robot/bittle-1/introduction", result);
    }

    @Test
    void givenAnOfflineRobot_whenExecuted_thenTheTextIsStillStored() {
        // Deliberately unlike SetRobotModeUseCase: editing the text must not
        // require the robot to be up. The boot resync pushes it later.
        doThrow(new AdapterUnavailableException("http://laika", new RuntimeException("refused")))
                .when(adapter).post(LAIKA, "/conversation/introduction",
                        Map.of("introduction", "I am Laika."));

        var result = useCase.execute("bittle-1", "I am Laika.", "gui");

        verify(introductions).save(result);
        verify(publisher).publish("/topic/robot/bittle-1/introduction", result);
    }

    @Test
    void givenBlankOrOversizedText_whenExecuted_thenItIsRejectedWithoutStoring() {
        assertThatThrownBy(() -> useCase.execute("bittle-1", "   ", "gui"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> useCase.execute("bittle-1", null, "gui"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> useCase.execute("bittle-1",
                "x".repeat(RobotIntroduction.MAX_CHARS + 1), "gui"))
                .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(introductions, adapter, publisher);
    }

    @Test
    void givenUnknownRobot_whenExecuted_thenRobotNotFoundIsThrownWithoutTouchingAnything() {
        assertThatThrownBy(() -> useCase.execute("ghost", "I am Laika.", "gui"))
                .isInstanceOf(RobotNotFoundException.class);
        verifyNoInteractions(introductions, adapter, publisher);
    }
}

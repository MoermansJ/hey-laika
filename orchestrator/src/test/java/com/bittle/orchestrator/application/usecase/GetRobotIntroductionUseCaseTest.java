package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.RobotIntroductionRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class GetRobotIntroductionUseCaseTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");

    private final Fleet fleet = new Fleet(List.of(LAIKA));
    private final RobotIntroductionRepositoryPort introductions =
            mock(RobotIntroductionRepositoryPort.class);
    private final GetRobotIntroductionUseCase useCase =
            new GetRobotIntroductionUseCase(fleet, introductions);

    @Test
    void givenAStoredRow_whenExecuted_thenItIsReturned() {
        var stored = new RobotIntroduction("bittle-1", "I am Laika.", Instant.EPOCH, "gui");
        when(introductions.find("bittle-1")).thenReturn(Optional.of(stored));

        assertThat(useCase.execute("bittle-1")).isEqualTo(stored);
    }

    @Test
    void givenNothingStored_whenExecuted_thenAnEmptyRowIsReturnedAndNothingIsWritten() {
        when(introductions.find("bittle-1")).thenReturn(Optional.empty());

        var result = useCase.execute("bittle-1");

        assertThat(result.text()).isEmpty();
        assertThat(result.stored()).isFalse();     // the adapter's compiled default is in use
        verify(introductions).find("bittle-1");
        verify(introductions, never()).save(any());     // a read never seeds a row
    }

    @Test
    void givenUnknownRobot_whenExecuted_thenRobotNotFoundIsThrown() {
        assertThatThrownBy(() -> useCase.execute("ghost"))
                .isInstanceOf(RobotNotFoundException.class);
    }
}

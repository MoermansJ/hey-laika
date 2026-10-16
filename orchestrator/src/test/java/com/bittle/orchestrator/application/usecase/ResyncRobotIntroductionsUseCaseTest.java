package com.bittle.orchestrator.application.usecase;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.application.port.out.RobotIntroductionRepositoryPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ResyncRobotIntroductionsUseCaseTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");
    private static final Robot MOCHA = new Robot("bittle-2", "Mocha", "bittle_x_v2", "http://mocha");

    private final Fleet fleet = new Fleet(List.of(LAIKA, MOCHA));
    private final RobotIntroductionRepositoryPort introductions =
            mock(RobotIntroductionRepositoryPort.class);
    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final ResyncRobotIntroductionsUseCase useCase =
            new ResyncRobotIntroductionsUseCase(fleet, introductions, adapter);

    @Test
    void givenStoredText_whenExecuted_thenOnlyRobotsWithARowArePushed() {
        when(introductions.find("bittle-1")).thenReturn(Optional.of(
                new RobotIntroduction("bittle-1", "I am Laika.", Instant.EPOCH, "gui")));
        when(introductions.find("bittle-2")).thenReturn(Optional.empty());

        useCase.execute();

        verify(adapter).post(LAIKA, "/conversation/introduction",
                Map.of("introduction", "I am Laika."));
        // Nothing stored for Mocha: she keeps the adapter's compiled default.
        verify(adapter, never()).post(eq(MOCHA), anyString(), any());
    }

    @Test
    void givenAnUnreachableRobot_whenExecuted_thenTheOthersAreStillPushed() {
        when(introductions.find("bittle-1")).thenReturn(Optional.of(
                new RobotIntroduction("bittle-1", "I am Laika.", Instant.EPOCH, "gui")));
        when(introductions.find("bittle-2")).thenReturn(Optional.of(
                new RobotIntroduction("bittle-2", "I am Mocha.", Instant.EPOCH, "gui")));
        doThrow(new AdapterUnavailableException("http://laika", new RuntimeException("refused")))
                .when(adapter).post(LAIKA, "/conversation/introduction",
                        Map.of("introduction", "I am Laika."));

        useCase.execute();

        verify(adapter).post(MOCHA, "/conversation/introduction",
                Map.of("introduction", "I am Mocha."));
    }
}

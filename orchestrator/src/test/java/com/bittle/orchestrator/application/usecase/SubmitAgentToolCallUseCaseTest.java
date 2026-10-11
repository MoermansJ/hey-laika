package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.service.AgentBehaviorService;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SubmitAgentToolCallUseCaseTest {

    private static final UUID DECISION = UUID.fromString("7c9e6679-7425-40de-944b-e07fc1f90ae7");

    private final AgentBehaviorService service = mock(AgentBehaviorService.class);
    private final SubmitAgentToolCallUseCase useCase = new SubmitAgentToolCallUseCase(
            new Fleet(List.of(new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika"))),
            service);

    @Test
    void givenValidCall_whenExecuted_thenItIsSubmittedWithTheParsedDecision() {
        var queued = new ArbiterSubmissionResponse(UUID.randomUUID(), "queued", null, 0);
        when(service.submitToolCall("bittle-1", "bark", "bark", DECISION)).thenReturn(queued);

        assertThat(useCase.execute("bittle-1", " bark ", " bark ", DECISION.toString()))
                .isSameAs(queued);
    }

    @Test
    void givenNoDecisionOrGoal_whenExecuted_thenNullsArePassedOn() {
        when(service.submitToolCall("bittle-1", "bark", null, null))
                .thenReturn(ArbiterSubmissionResponse.rejected("x"));

        useCase.execute("bittle-1", "bark", " ", "");

        verify(service).submitToolCall("bittle-1", "bark", null, null);
    }

    @Test
    void givenInvalidDecisionId_whenExecuted_thenRejectedAsBadRequest() {
        assertThatThrownBy(() -> useCase.execute("bittle-1", "bark", null, "nope"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("decisionId");
        verifyNoInteractions(service);
    }

    @Test
    void givenUnknownRobot_whenExecuted_thenNotFound() {
        assertThatThrownBy(() -> useCase.execute("ghost", "bark", null, null))
                .isInstanceOf(RobotNotFoundException.class);
        verify(service, org.mockito.Mockito.never()).submitToolCall(any(), any(), any(), any());
    }
}

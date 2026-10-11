package com.bittle.orchestrator.domain.behavior;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class ArbiterSubmissionTest {

    @Test
    void givenAgentToolCall_whenRequestBuilt_thenPriorityThreeSourceAgentAndCauseCarryDecision() {
        var request = ArbiterSubmissionRequest.forAgent("look_up", "look_upward", "d-1");

        assertThat(request.priority()).isEqualTo(3);
        assertThat(request.source()).isEqualTo("agent");
        assertThat(request.goal()).isEqualTo("look_upward");
        assertThat(request.cause()).containsEntry("type", "agent").containsEntry("decisionId", "d-1");
        assertThat(request.decisionId()).isEqualTo("d-1");
        assertThat(request.parameters()).isNull();
    }

    @Test
    void givenBlankBehavior_whenRequestBuilt_thenRejected() {
        assertThatThrownBy(() -> ArbiterSubmissionRequest.forAgent(" ", "g", "d"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void givenRequestWithoutCause_whenDecisionIdRead_thenNull() {
        var request = new ArbiterSubmissionRequest("wave", "manual", 4, null, null, null);

        assertThat(request.decisionId()).isNull();
    }

    @Test
    void givenStatuses_whenAcceptanceChecked_thenOnlyRejectedIsNotAccepted() {
        var run = UUID.randomUUID();

        assertThat(new ArbiterSubmissionResponse(run, "executing", null, 0).isAccepted()).isTrue();
        assertThat(new ArbiterSubmissionResponse(run, "queued", null, 1).isAccepted()).isTrue();
        assertThat(new ArbiterSubmissionResponse(run, "preempting", null, 0).isAccepted()).isTrue();
        var rejected = ArbiterSubmissionResponse.rejected("cooldown");
        assertThat(rejected.isAccepted()).isFalse();
        assertThat(rejected.runLogId()).isNull();
        assertThat(rejected.message()).isEqualTo("cooldown");
    }
}

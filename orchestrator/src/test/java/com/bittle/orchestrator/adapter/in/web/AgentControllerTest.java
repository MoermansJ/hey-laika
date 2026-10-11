package com.bittle.orchestrator.adapter.in.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.application.usecase.GetAgentToolsUseCase;
import com.bittle.orchestrator.application.usecase.GetLearnedPatternsUseCase;
import com.bittle.orchestrator.application.usecase.SubmitAgentToolCallUseCase;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import java.util.UUID;
import org.springframework.http.MediaType;
import com.bittle.orchestrator.domain.behavior.AgentToolCatalog;
import com.bittle.orchestrator.domain.behavior.OperatingMode;
import com.bittle.orchestrator.domain.behavior.LearnedPattern;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

@WebMvcTest(AgentController.class)
@MockitoBean(types = {GetLearnedPatternsUseCase.class, GetAgentToolsUseCase.class,
        SubmitAgentToolCallUseCase.class, OrchestratorMetricsPort.class})
class AgentControllerTest {

    private static final Instant T0 = Instant.parse("2026-10-11T21:00:00Z");

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private GetLearnedPatternsUseCase getLearnedPatterns;

    @Autowired
    private GetAgentToolsUseCase getAgentTools;

    @Autowired
    private SubmitAgentToolCallUseCase submitToolCall;

    @Test
    void givenToolCall_whenSubmitted_thenTheArbiterAnswerIsReturned() {
        var run = UUID.fromString("0f8fad5b-d9cb-469f-a165-70867728950e");
        when(submitToolCall.execute("bittle-1", "look_upward", "look_upward",
                "7c9e6679-7425-40de-944b-e07fc1f90ae7"))
                .thenReturn(new ArbiterSubmissionResponse(run, "queued", null, 1));

        var result = mvc.post().uri("/api/v1/agent/bittle-1/submit-tool")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"toolName": "look_upward", "goal": "look_upward",
                         "decisionId": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}
                        """)
                .exchange();

        assertThat(result).hasStatusOk().bodyJson().isLenientlyEqualTo("""
                {"runLogId": "0f8fad5b-d9cb-469f-a165-70867728950e", "status": "queued",
                 "position": 1}
                """);
    }

    @Test
    void givenRejectedCall_whenSubmitted_thenRejectionIsReturnedWithItsMessage() {
        when(submitToolCall.execute("bittle-1", "bark", null, null))
                .thenReturn(ArbiterSubmissionResponse.rejected("cooldown"));

        var result = mvc.post().uri("/api/v1/agent/bittle-1/submit-tool")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"toolName\": \"bark\"}")
                .exchange();

        assertThat(result).hasStatusOk().bodyJson().isLenientlyEqualTo("""
                {"status": "rejected", "message": "cooldown"}
                """);
    }

    @Test
    void givenBadDecisionId_whenSubmitted_thenBadRequest() {
        when(submitToolCall.execute("bittle-1", "bark", null, "nope"))
                .thenThrow(new IllegalArgumentException("decisionId must be a UUID: nope"));

        var result = mvc.post().uri("/api/v1/agent/bittle-1/submit-tool")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"toolName\": \"bark\", \"decisionId\": \"nope\"}")
                .exchange();

        assertThat(result).hasStatus(HttpStatus.BAD_REQUEST)
                .bodyJson().extractingPath("$.error").isEqualTo("bad_request");
    }

    @Test
    void givenStationaryRobot_whenToolsRequested_thenStationaryToolsAreReturned() {
        when(getAgentTools.execute("bittle-1"))
                .thenReturn(AgentToolCatalog.toolsFor(OperatingMode.STATIONARY));

        var result = mvc.get().uri("/api/v1/agent/bittle-1/tools").exchange();

        assertThat(result).hasStatusOk().bodyJson().extractingPath("$[0]").isEqualTo(
                java.util.Map.of("name", "look_left", "description", "Face left",
                        "category", "postural"));
        assertThat(result).bodyJson().extractingPath("$.length()").isEqualTo(7);
    }

    @Test
    void givenUnknownRobot_whenToolsRequested_thenNotFound() {
        when(getAgentTools.execute("ghost")).thenThrow(new RobotNotFoundException("ghost"));

        var result = mvc.get().uri("/api/v1/agent/ghost/tools").exchange();

        assertThat(result).hasStatus(HttpStatus.NOT_FOUND)
                .bodyJson().extractingPath("$.error").isEqualTo("robot_not_found");
    }

    @Test
    void givenPatterns_whenQueried_thenTheyAreReturnedAsDtosInOrder() {
        var best = LearnedPattern.discovered("bittle-1", "look_upward",
                List.of("raise_right_paw", "lower_left_paw"), T0).withStats(12, 11, T0, T0);
        var worse = LearnedPattern.discovered("bittle-1", "look_upward", List.of("head_pan"), T0)
                .withStats(20, 3, T0.plusSeconds(60), T0);
        when(getLearnedPatterns.execute("bittle-1", "look_upward")).thenReturn(List.of(best, worse));

        var result = mvc.get().uri("/api/v1/agent/bittle-1/patterns?goal=look_upward").exchange();

        assertThat(result).hasStatusOk().bodyJson().isLenientlyEqualTo("""
                [ {"toolCombination": ["raise_right_paw", "lower_left_paw"],
                   "successRate": 0.9166666666666666, "attempts": 12, "successes": 11,
                   "lastUsed": "2026-10-11T21:00:00Z"},
                  {"toolCombination": ["head_pan"], "successRate": 0.15, "attempts": 20,
                   "successes": 3, "lastUsed": "2026-10-11T21:01:00Z"} ]
                """);
    }

    @Test
    void givenNoPatterns_whenQueried_thenEmptyArray() {
        when(getLearnedPatterns.execute("bittle-1", "bark")).thenReturn(List.of());

        var result = mvc.get().uri("/api/v1/agent/bittle-1/patterns?goal=bark").exchange();

        assertThat(result).hasStatusOk().bodyJson().isLenientlyEqualTo("[]");
    }

    @Test
    void givenUnknownRobot_whenQueried_thenNotFound() {
        when(getLearnedPatterns.execute("ghost", "bark"))
                .thenThrow(new RobotNotFoundException("ghost"));

        var result = mvc.get().uri("/api/v1/agent/ghost/patterns?goal=bark").exchange();

        assertThat(result).hasStatus(HttpStatus.NOT_FOUND)
                .bodyJson().extractingPath("$.error").isEqualTo("robot_not_found");
    }

    @Test
    void givenBlankGoal_whenQueried_thenBadRequest() {
        when(getLearnedPatterns.execute("bittle-1", " "))
                .thenThrow(new IllegalArgumentException("goal is required"));

        var result = mvc.get().uri("/api/v1/agent/bittle-1/patterns").param("goal", " ")
                .exchange();

        assertThat(result).hasStatus(HttpStatus.BAD_REQUEST)
                .bodyJson().extractingPath("$.error").isEqualTo("bad_request");
    }

    @Test
    void givenMissingGoal_whenQueried_thenBadRequest() {
        var result = mvc.get().uri("/api/v1/agent/bittle-1/patterns").exchange();

        assertThat(result).hasStatus(HttpStatus.BAD_REQUEST);
    }
}

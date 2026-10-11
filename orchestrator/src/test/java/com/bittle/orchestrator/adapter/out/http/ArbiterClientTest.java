package com.bittle.orchestrator.adapter.out.http;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withResourceNotFound;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import java.net.SocketTimeoutException;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class ArbiterClientTest {

    private static final String BASE = "http://dog:5000/api/robots/bittle-1";
    private static final UUID RUN = UUID.fromString("0f8fad5b-d9cb-469f-a165-70867728950e");

    private MockRestServiceServer server;
    private ArbiterClient client;

    @BeforeEach
    void setUp() {
        var builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        var fleet = new Fleet(List.of(new Robot("bittle-1", "Laika", "bittle_x_v2",
                "http://dog:5000")));
        client = new ArbiterClient(fleet, builder.build());
    }

    // ---- submit ---------------------------------------------------------------

    @Test
    void givenAgentRequest_whenSubmitted_thenInvokeCarriesAgentProvenanceAndRunIdIsParsed() {
        server.expect(requestTo(BASE + "/arbiter/invoke"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.behavior").value("look_up"))
                .andExpect(jsonPath("$.source").value("agent"))
                .andExpect(jsonPath("$.priority").value(3))
                .andExpect(jsonPath("$.decisionId").value("d-1"))
                .andExpect(jsonPath("$.goal").value("look_upward"))
                .andRespond(withSuccess("""
                        {"robotId": "bittle-1", "behavior": "look_up",
                         "status": "executing", "position": 0, "runId": "%s"}
                        """.formatted(RUN), MediaType.APPLICATION_JSON));

        var response = client.submit("bittle-1",
                ArbiterSubmissionRequest.forAgent("look_up", "look_upward", "d-1"));

        assertThat(response.status()).isEqualTo(ArbiterSubmissionResponse.EXECUTING);
        assertThat(response.runLogId()).isEqualTo(RUN);
        assertThat(response.position()).isZero();
        assertThat(response.message()).isNull();
        assertThat(response.isAccepted()).isTrue();
        server.verify();
    }

    @Test
    void givenArbiterRejects_whenSubmitted_thenReasonBecomesMessage() {
        server.expect(requestTo(BASE + "/arbiter/invoke"))
                .andRespond(withSuccess("""
                        {"robotId": "bittle-1", "behavior": "look_up",
                         "status": "rejected", "reason": "cooldown"}
                        """, MediaType.APPLICATION_JSON));

        var response = client.submit("bittle-1",
                ArbiterSubmissionRequest.forAgent("look_up", "look_upward", "d-2"));

        assertThat(response.isAccepted()).isFalse();
        assertThat(response.message()).isEqualTo("cooldown");
        assertThat(response.runLogId()).isNull();
    }

    @Test
    void givenAdapterHttpError_whenSubmitted_thenRejectedWithStatusAndBody() {
        server.expect(requestTo(BASE + "/arbiter/invoke"))
                .andRespond(withStatus(HttpStatus.BAD_REQUEST)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"error\":\"bad_request\",\"message\":\"'behavior' required\"}"));

        var response = client.submit("bittle-1",
                ArbiterSubmissionRequest.forAgent("look_up", null, "d-3"));

        assertThat(response.status()).isEqualTo(ArbiterSubmissionResponse.REJECTED);
        assertThat(response.message()).startsWith("Adapter returned HTTP 400")
                .contains("'behavior' required");
    }

    @Test
    void givenAdapterTimesOut_whenSubmitted_thenRejectedAsConnectionError() {
        server.expect(requestTo(BASE + "/arbiter/invoke"))
                .andRespond(request -> {
                    throw new SocketTimeoutException("Read timed out");
                });

        var response = client.submit("bittle-1",
                ArbiterSubmissionRequest.forAgent("look_up", "look_upward", "d-4"));

        assertThat(response.status()).isEqualTo(ArbiterSubmissionResponse.REJECTED);
        assertThat(response.message()).startsWith("Connection error").contains("Read timed out");
    }

    @Test
    void givenUnknownRobot_whenSubmitted_thenRejectedWithoutCallingTheAdapter() {
        var response = client.submit("ghost",
                ArbiterSubmissionRequest.forAgent("look_up", "look_upward", "d-5"));

        assertThat(response.isAccepted()).isFalse();
        assertThat(response.message()).contains("ghost");
        server.verify();
    }

    @Test
    void givenRequestWithoutGoalOrDecision_whenBodyBuilt_thenOptionalFieldsAreOmitted() {
        var request = new ArbiterSubmissionRequest("wave", "manual", null, null, null, null);

        assertThat(ArbiterClient.invokeBody(request))
                .containsOnlyKeys("behavior", "source")
                .containsEntry("behavior", "wave")
                .containsEntry("source", "manual");
    }

    // ---- getRunLog ------------------------------------------------------------

    @Test
    void givenFinishedRun_whenRunLogRead_thenItIsMappedToBehaviorRunLog() {
        server.expect(requestTo(BASE + "/behavior/run-log/" + RUN))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("""
                        {"robotId": "bittle-1", "id": "%s", "behavior": "look_up",
                         "source": "agent", "priority": 3, "status": "complete",
                         "detail": "",
                         "cause": {"type": "agent", "decisionId": "d-1", "goal": "look_upward"},
                         "preemptedBy": null,
                         "startedAt": "2026-10-11T12:00:00.000000+00:00",
                         "endedAt": "2026-10-11T12:00:01.250000+00:00",
                         "outcome": {"success": true, "confidence": 0.87,
                                     "reason": "centered", "evaluator_version": "1.0",
                                     "evaluated_at": "2026-10-11T12:00:02Z"},
                         "sensorDelta": {"pitch": 12}}
                        """.formatted(RUN), MediaType.APPLICATION_JSON));

        var runLog = client.getRunLog("bittle-1", RUN).orElseThrow();

        assertThat(runLog.id()).isEqualTo(RUN);
        assertThat(runLog.robotId()).isEqualTo("bittle-1");
        assertThat(runLog.behaviorName()).isEqualTo("look_up");
        assertThat(runLog.source()).isEqualTo("agent");
        assertThat(runLog.priority()).isEqualTo(3);
        assertThat(runLog.goal()).isEqualTo("look_upward");
        assertThat(runLog.cause()).containsEntry("decisionId", "d-1");
        assertThat(runLog.timestamp()).isEqualTo(Instant.parse("2026-10-11T12:00:00Z"));
        assertThat(runLog.completedAt()).isEqualTo(Instant.parse("2026-10-11T12:00:01.25Z"));
        assertThat(runLog.executionTimeMs()).isEqualTo(1250L);
        assertThat(runLog.hasOutcome()).isTrue();
        assertThat(runLog.outcome().success()).isTrue();
        assertThat(runLog.outcome().confidence()).isEqualTo(0.87);
        assertThat(runLog.outcome().evaluatorVersion()).isEqualTo("1.0");
        assertThat(runLog.sensorDelta()).containsEntry("pitch", 12);
    }

    @Test
    void givenRunningRun_whenRunLogRead_thenItHasNoCompletionOrOutcome() {
        server.expect(requestTo(BASE + "/behavior/run-log/" + RUN))
                .andRespond(withSuccess("""
                        {"id": "%s", "behavior": "look_up", "source": "agent", "priority": 3,
                         "status": "running", "cause": {"type": "agent", "decisionId": "d-1"},
                         "startedAt": "2026-10-11T12:00:00+00:00", "endedAt": null,
                         "outcome": null, "sensorDelta": null}
                        """.formatted(RUN), MediaType.APPLICATION_JSON));

        var runLog = client.getRunLog("bittle-1", RUN).orElseThrow();

        assertThat(runLog.completedAt()).isNull();
        assertThat(runLog.executionTimeMs()).isNull();
        assertThat(runLog.goal()).isNull();
        assertThat(runLog.hasOutcome()).isFalse();
    }

    @Test
    void givenRunNotStartedYet_whenRunLogRead_thenEmpty() {
        server.expect(requestTo(BASE + "/behavior/run-log/" + RUN))
                .andRespond(withResourceNotFound());

        assertThat(client.getRunLog("bittle-1", RUN)).isEmpty();
    }

    @Test
    void givenAdapterDown_whenRunLogRead_thenEmpty() {
        server.expect(requestTo(BASE + "/behavior/run-log/" + RUN))
                .andRespond(request -> {
                    throw new java.net.ConnectException("Connection refused");
                });

        assertThat(client.getRunLog("bittle-1", RUN)).isEmpty();
    }

    @Test
    void givenUnknownRobot_whenRunLogRead_thenEmpty() {
        assertThat(client.getRunLog("ghost", RUN)).isEmpty();
        server.verify();
    }

    // ---- syncOutcome ----------------------------------------------------------

    @Test
    void givenOutcome_whenSynced_thenPutCarriesSnakeCaseFields() {
        server.expect(requestTo(BASE + "/behavior/run-log/" + RUN + "/outcome"))
                .andExpect(method(HttpMethod.PUT))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.confidence").value(0.87))
                .andExpect(jsonPath("$.reason").value("centered"))
                .andExpect(jsonPath("$.evaluator_version").value("1.0"))
                .andExpect(jsonPath("$.evaluated_at").value("2026-10-11T12:00:02Z"))
                .andRespond(withSuccess("{\"status\":\"updated\"}", MediaType.APPLICATION_JSON));

        boolean synced = client.syncOutcome("bittle-1", RUN, new OutcomeEvaluation(true, 0.87,
                "centered", "1.0", Instant.parse("2026-10-11T12:00:02Z")));

        assertThat(synced).isTrue();
        server.verify();
    }

    @Test
    void givenAdapterError_whenOutcomeSynced_thenFalseAndNoException() {
        server.expect(requestTo(BASE + "/behavior/run-log/" + RUN + "/outcome"))
                .andRespond(withServerError());

        boolean synced = client.syncOutcome("bittle-1", RUN, new OutcomeEvaluation(null, null,
                "no checker", "1.0", Instant.parse("2026-10-11T12:00:02Z")));

        assertThat(synced).isFalse();
    }

    @Test
    void givenUnknownRobot_whenOutcomeSynced_thenFalse() {
        assertThat(client.syncOutcome("ghost", RUN, new OutcomeEvaluation(true, 1.0, "", "1.0",
                Instant.parse("2026-10-11T12:00:02Z")))).isFalse();
        server.verify();
    }
}

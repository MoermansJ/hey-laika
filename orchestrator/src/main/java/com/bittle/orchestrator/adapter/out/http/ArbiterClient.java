package com.bittle.orchestrator.adapter.out.http;

import com.bittle.orchestrator.application.port.out.ArbiterPort;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionRequest;
import com.bittle.orchestrator.domain.behavior.ArbiterSubmissionResponse;
import com.bittle.orchestrator.domain.behavior.BehaviorRunLog;
import com.bittle.orchestrator.domain.behavior.OutcomeEvaluation;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/**
 * REST client for the Python adapter's behavior arbiter
 * (AGENT_TOOL_COMPOSITION_DESIGN.md §5.1, AGENT-04).
 *
 * <p>The design sketches a single {@code adapter.url}; in this codebase every
 * robot has its own adapter ({@link Robot#serviceUrl()}) and the adapter's
 * routes are robot-scoped, so the client resolves the robot from the
 * {@link Fleet} and calls:
 * <ul>
 *   <li>submit — {@code POST /api/robots/{id}/arbiter/invoke}</li>
 *   <li>getRunLog — {@code GET /api/robots/{id}/behavior/run-log/{runId}}</li>
 *   <li>syncOutcome — {@code PUT /api/robots/{id}/behavior/run-log/{runId}/outcome}</li>
 * </ul>
 * Timeouts come from {@code arbiter.*} properties (see {@code ArbiterProperties}).
 * Failures never escape: see {@link ArbiterPort}.
 */
@Component
public class ArbiterClient implements ArbiterPort {

    private static final Logger log = LoggerFactory.getLogger(ArbiterClient.class);
    private static final int MAX_ERROR_BODY = 200;

    private final Fleet fleet;
    private final RestClient http;

    public ArbiterClient(Fleet fleet, @Qualifier("arbiterRestClient") RestClient arbiterRestClient) {
        this.fleet = fleet;
        this.http = arbiterRestClient;
    }

    @Override
    public ArbiterSubmissionResponse submit(String robotId, ArbiterSubmissionRequest request) {
        Robot robot;
        try {
            robot = fleet.get(robotId);
        } catch (RobotNotFoundException e) {
            log.warn("Arbiter submit for unknown robot {}", robotId);
            return ArbiterSubmissionResponse.rejected("Unknown robot: " + robotId);
        }
        try {
            Map<?, ?> body = http.post().uri(robotUri(robot, "/arbiter/invoke"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(invokeBody(request))
                    .retrieve().body(Map.class);
            ArbiterSubmissionResponse response = toResponse(body);
            log.debug("Arbiter submit {} for {} -> {}", request.behaviorName(), robotId,
                    response.status());
            return response;
        } catch (RestClientResponseException e) {
            log.warn("Arbiter submit {} for {} failed: HTTP {}", request.behaviorName(), robotId,
                    e.getStatusCode().value());
            return ArbiterSubmissionResponse.rejected("Adapter returned HTTP "
                    + e.getStatusCode().value() + errorDetail(e));
        } catch (ResourceAccessException e) {
            log.warn("Arbiter submit {} for {} failed: {}", request.behaviorName(), robotId,
                    e.getMessage());
            return ArbiterSubmissionResponse.rejected("Connection error: " + e.getMessage());
        } catch (RestClientException | IllegalArgumentException e) {
            log.warn("Arbiter submit {} for {} returned an unreadable answer: {}",
                    request.behaviorName(), robotId, e.getMessage());
            return ArbiterSubmissionResponse.rejected("Invalid adapter response: " + e.getMessage());
        }
    }

    @Override
    public Optional<BehaviorRunLog> getRunLog(String robotId, UUID runLogId) {
        Robot robot;
        try {
            robot = fleet.get(robotId);
        } catch (RobotNotFoundException e) {
            log.warn("Run-log read for unknown robot {}", robotId);
            return Optional.empty();
        }
        try {
            Map<?, ?> body = http.get()
                    .uri(robotUri(robot, "/behavior/run-log/" + runLogId))
                    .retrieve().body(Map.class);
            return Optional.ofNullable(body).map(m -> toRunLog(robotId, runLogId, m));
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() != HttpStatus.NOT_FOUND.value()) {
                log.warn("Run-log read {} for {} failed: HTTP {}", runLogId, robotId,
                        e.getStatusCode().value());
            }
            return Optional.empty();
        } catch (RestClientException | IllegalArgumentException | DateTimeParseException e) {
            log.warn("Run-log read {} for {} failed: {}", runLogId, robotId, e.getMessage());
            return Optional.empty();
        }
    }

    @Override
    public boolean syncOutcome(String robotId, UUID runLogId, OutcomeEvaluation outcome) {
        Robot robot;
        try {
            robot = fleet.get(robotId);
        } catch (RobotNotFoundException e) {
            log.warn("Outcome sync for unknown robot {}", robotId);
            return false;
        }
        try {
            http.put().uri(robotUri(robot, "/behavior/run-log/" + runLogId + "/outcome"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(outcomeBody(outcome))
                    .retrieve().toBodilessEntity();
            return true;
        } catch (RestClientResponseException e) {
            log.warn("Outcome sync {} for {} failed: HTTP {}", runLogId, robotId,
                    e.getStatusCode().value());
            return false;
        } catch (RestClientException e) {
            log.warn("Outcome sync {} for {} failed: {}", runLogId, robotId, e.getMessage());
            return false;
        }
    }

    static Map<String, Object> invokeBody(ArbiterSubmissionRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("behavior", request.behaviorName());
        body.put("source", request.source());
        if (request.priority() != null) {
            body.put("priority", request.priority());
        }
        if (request.decisionId() != null) {
            body.put("decisionId", request.decisionId());
        }
        if (request.goal() != null) {
            body.put("goal", request.goal());
        }
        if (request.parameters() != null && !request.parameters().isEmpty()) {
            body.put("parameters", request.parameters());
        }
        return body;
    }

    static Map<String, Object> outcomeBody(OutcomeEvaluation outcome) {
        // snake_case: the adapter's OutcomeEvaluation.from_dict reads both, the
        // PUT contract (AGENT-06) documents snake_case.
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("success", outcome.success());
        body.put("confidence", outcome.confidence());
        body.put("reason", outcome.reason());
        body.put("evaluator_version", outcome.evaluatorVersion());
        body.put("evaluated_at", outcome.evaluatedAt().toString());
        return body;
    }

    static ArbiterSubmissionResponse toResponse(Map<?, ?> body) {
        if (body == null) {
            return ArbiterSubmissionResponse.rejected("Empty adapter response");
        }
        Object status = body.get("status");
        if (status == null) {
            return ArbiterSubmissionResponse.rejected("Adapter response has no status");
        }
        Object reason = body.get("reason");
        if (reason == null) {
            reason = body.get("message");
        }
        Object position = body.get("position");
        return new ArbiterSubmissionResponse(
                uuid(body.get("runId")),
                status.toString(),
                reason == null ? null : reason.toString(),
                position instanceof Number n ? n.intValue() : null);
    }

    @SuppressWarnings("unchecked")
    static BehaviorRunLog toRunLog(String robotId, UUID requestedId, Map<?, ?> body) {
        UUID id = Optional.ofNullable(uuid(body.get("id"))).orElse(requestedId);
        Instant startedAt = instant(body.get("startedAt"));
        Instant endedAt = instant(body.get("endedAt"));
        Map<String, Object> cause = body.get("cause") instanceof Map<?, ?> m
                ? (Map<String, Object>) m : null;
        Object goal = cause == null ? null : cause.get("goal");
        Map<String, Object> sensorDelta = body.get("sensorDelta") instanceof Map<?, ?> m
                ? (Map<String, Object>) m : null;
        Long executionTimeMs = startedAt != null && endedAt != null
                ? Duration.between(startedAt, endedAt).toMillis() : null;
        Object priority = body.get("priority");
        Instant timestamp = startedAt != null ? startedAt : Instant.now();
        return new BehaviorRunLog(id, robotId, timestamp, endedAt,
                string(body.get("behavior")), string(body.get("source")),
                priority instanceof Number n ? n.intValue() : null,
                cause, executionTimeMs, string(body.get("preemptedBy")),
                goal == null ? null : goal.toString(),
                outcome(body.get("outcome")), sensorDelta, timestamp, endedAt);
    }

    private static OutcomeEvaluation outcome(Object raw) {
        if (!(raw instanceof Map<?, ?> m)) {
            return null;
        }
        Instant evaluatedAt = instant(first(m, "evaluated_at", "evaluatedAt"));
        if (evaluatedAt == null) {
            return null;
        }
        Object success = m.get("success");
        Object confidence = m.get("confidence");
        return new OutcomeEvaluation(
                success instanceof Boolean b ? b : null,
                confidence instanceof Number n ? n.doubleValue() : null,
                string(m.get("reason")),
                string(first(m, "evaluator_version", "evaluatorVersion")),
                evaluatedAt);
    }

    private static Object first(Map<?, ?> map, String key, String fallback) {
        Object value = map.get(key);
        return value != null ? value : map.get(fallback);
    }

    private static UUID uuid(Object raw) {
        if (raw == null) {
            return null;
        }
        try {
            return UUID.fromString(raw.toString());
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private static Instant instant(Object raw) {
        if (raw == null || raw.toString().isBlank()) {
            return null;
        }
        String text = raw.toString();
        try {
            return OffsetDateTime.parse(text).toInstant();
        } catch (DateTimeParseException e) {
            // Naive timestamps from the adapter are UTC.
            return Instant.parse(text.endsWith("Z") ? text : text + "Z");
        }
    }

    private static String string(Object raw) {
        return raw == null ? null : raw.toString();
    }

    private static String errorDetail(RestClientResponseException e) {
        String body = e.getResponseBodyAsString();
        if (body == null || body.isBlank()) {
            return "";
        }
        return ": " + (body.length() > MAX_ERROR_BODY ? body.substring(0, MAX_ERROR_BODY) : body)
                .strip();
    }

    private static String robotUri(Robot robot, String path) {
        return robot.serviceUrl() + "/api/robots/" + robot.id() + path;
    }
}

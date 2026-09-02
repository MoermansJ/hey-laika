package com.bittle.orchestrator.adapter.in.web;

import com.bittle.orchestrator.application.BehaviorLoopRunningException;
import com.bittle.orchestrator.application.port.out.AdapterErrorException;
import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.domain.fleet.RobotNotFoundException;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    private final OrchestratorMetricsPort metrics;

    public GlobalExceptionHandler(OrchestratorMetricsPort metrics) {
        this.metrics = metrics;
    }

    @ExceptionHandler(RobotNotFoundException.class)
    public ResponseEntity<Map<String, String>> robotNotFound(RobotNotFoundException e) {
        return error(HttpStatus.NOT_FOUND, "robot_not_found", e.getMessage());
    }

    @ExceptionHandler(BehaviorLoopRunningException.class)
    public ResponseEntity<Map<String, String>> loopRunning(BehaviorLoopRunningException e) {
        return error(HttpStatus.CONFLICT, "behavior_loop_running", e.getMessage());
    }

    @ExceptionHandler(AdapterUnavailableException.class)
    public ResponseEntity<Map<String, String>> adapterDown(AdapterUnavailableException e) {
        log.warn("Adapter unavailable: {}", e.getMessage());
        metrics.recordAdapterUnavailable();
        return error(HttpStatus.BAD_GATEWAY, "adapter_unavailable", e.getMessage());
    }

    /** Unknown action/event names on the behavior API. */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException e) {
        return error(HttpStatus.BAD_REQUEST, "bad_request", e.getMessage());
    }

    /** Forward the adapter's own error responses (404 unknown animation, 503 missing key, ...). */
    @ExceptionHandler(AdapterErrorException.class)
    public ResponseEntity<String> adapterError(AdapterErrorException e) {
        return ResponseEntity.status(e.getStatus())
                .contentType(MediaType.APPLICATION_JSON)
                .body(e.getBody());
    }

    private static ResponseEntity<Map<String, String>> error(HttpStatus status, String code,
                                                             String message) {
        return ResponseEntity.status(status).body(Map.of("error", code, "message", message));
    }
}

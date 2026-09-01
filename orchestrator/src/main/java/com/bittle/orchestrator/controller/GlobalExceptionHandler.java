package com.bittle.orchestrator.controller;

import com.bittle.orchestrator.exception.AdapterErrorException;
import com.bittle.orchestrator.exception.AdapterUnavailableException;
import com.bittle.orchestrator.exception.RobotNotFoundException;
import com.bittle.orchestrator.metrics.MetricsService;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    // ObjectProvider: @WebMvcTest slices run with observability disabled and
    // provide no MeterRegistry — the counter is simply skipped there.
    private final ObjectProvider<MeterRegistry> meterRegistry;

    public GlobalExceptionHandler(ObjectProvider<MeterRegistry> meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @ExceptionHandler(RobotNotFoundException.class)
    public ResponseEntity<Map<String, String>> robotNotFound(RobotNotFoundException e) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "robot_not_found", "message", e.getMessage()));
    }

    @ExceptionHandler(AdapterUnavailableException.class)
    public ResponseEntity<Map<String, String>> adapterDown(AdapterUnavailableException e) {
        log.warn("Adapter unavailable: {}", e.getMessage());
        meterRegistry.ifAvailable(registry ->
                registry.counter(MetricsService.ADAPTER_UNAVAILABLE_COUNTER).increment());
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(Map.of("error", "adapter_unavailable", "message", e.getMessage()));
    }

    /** Unknown action/event names on the behavior API. */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "bad_request", "message", e.getMessage()));
    }

    /** Forward the adapter's own error responses (404 unknown animation, 503 missing key, ...). */
    @ExceptionHandler(AdapterErrorException.class)
    public ResponseEntity<String> adapterError(AdapterErrorException e) {
        return ResponseEntity.status(e.getStatus())
                .contentType(MediaType.APPLICATION_JSON)
                .body(e.getBody());
    }
}

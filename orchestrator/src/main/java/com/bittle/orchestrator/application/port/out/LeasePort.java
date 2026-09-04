package com.bittle.orchestrator.application.port.out;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

public interface LeasePort {

    boolean acquire(String key, String owner, Duration ttl);

    void release(String key, String owner);

    Optional<Lease> holder(String key);

    record Lease(String key, String owner, Instant expiresAt) {
    }
}

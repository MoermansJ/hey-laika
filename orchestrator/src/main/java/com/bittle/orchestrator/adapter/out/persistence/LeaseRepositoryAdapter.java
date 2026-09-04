package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.application.port.out.LeasePort;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Component;

@Component
public class LeaseRepositoryAdapter implements LeasePort {

    private final LeaseJpaRepository repository;

    public LeaseRepositoryAdapter(LeaseJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean acquire(String key, String owner, Duration ttl) {
        var now = Instant.now();
        var until = now.plus(ttl);
        if (repository.claim(key, owner, now, until) > 0) {
            return true;
        }
        if (repository.existsById(key)) {
            return false;
        }
        try {
            repository.saveAndFlush(new LeaseEntity(key, owner, until));
            return true;
        } catch (DataIntegrityViolationException e) {
            return false;
        }
    }

    @Override
    public void release(String key, String owner) {
        repository.expire(key, owner, Instant.now());
    }

    @Override
    public Optional<Lease> holder(String key) {
        var now = Instant.now();
        return repository.findById(key)
                .filter(lease -> lease.getExpiresAt().isAfter(now))
                .map(lease -> new Lease(lease.getLeaseKey(), lease.getHolder(), lease.getExpiresAt()));
    }
}

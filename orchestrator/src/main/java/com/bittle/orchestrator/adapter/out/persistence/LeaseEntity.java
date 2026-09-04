package com.bittle.orchestrator.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "leases")
public class LeaseEntity {

    @Id
    @Column(name = "lease_key")
    private String leaseKey;

    @Column(nullable = false)
    private String holder;

    @Column(nullable = false)
    private Instant expiresAt;

    protected LeaseEntity() {
    }

    public LeaseEntity(String leaseKey, String holder, Instant expiresAt) {
        this.leaseKey = leaseKey;
        this.holder = holder;
        this.expiresAt = expiresAt;
    }

    public String getLeaseKey() { return leaseKey; }
    public String getHolder() { return holder; }
    public Instant getExpiresAt() { return expiresAt; }
}

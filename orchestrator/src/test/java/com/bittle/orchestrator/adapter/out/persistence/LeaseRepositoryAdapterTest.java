package com.bittle.orchestrator.adapter.out.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.bittle.orchestrator.application.port.out.LeasePort;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@DataJpaTest
@Import(LeaseRepositoryAdapter.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class LeaseRepositoryAdapterTest {

    private static final Duration MINUTE = Duration.ofMinutes(1);

    @Autowired
    private LeaseRepositoryAdapter leases;

    @Test
    void givenFreeKey_whenAcquired_thenItIsHeldByTheOwner() {
        assertThat(leases.acquire("free", "a", MINUTE)).isTrue();

        assertThat(leases.holder("free")).map(LeasePort.Lease::owner).contains("a");
    }

    @Test
    void givenHeldKey_whenAnotherOwnerAcquires_thenItIsRefused() {
        leases.acquire("held", "a", MINUTE);

        assertThat(leases.acquire("held", "b", MINUTE)).isFalse();
        assertThat(leases.holder("held")).map(LeasePort.Lease::owner).contains("a");
    }

    @Test
    void givenHeldKey_whenTheSameOwnerAcquires_thenItIsRenewed() {
        leases.acquire("renew", "a", MINUTE);
        var first = leases.holder("renew").orElseThrow().expiresAt();

        assertThat(leases.acquire("renew", "a", Duration.ofMinutes(5))).isTrue();

        assertThat(leases.holder("renew").orElseThrow().expiresAt()).isAfter(first);
    }

    @Test
    void givenExpiredLease_whenAnotherOwnerAcquires_thenItIsTakenOver() {
        leases.acquire("expired", "a", Duration.ofSeconds(-1));
        assertThat(leases.holder("expired")).isEmpty();

        assertThat(leases.acquire("expired", "b", MINUTE)).isTrue();

        assertThat(leases.holder("expired")).map(LeasePort.Lease::owner).contains("b");
    }

    @Test
    void givenReleasedLease_whenAnotherOwnerAcquires_thenItIsTakenOver() {
        leases.acquire("released", "a", MINUTE);

        leases.release("released", "a");

        assertThat(leases.holder("released")).isEmpty();
        assertThat(leases.acquire("released", "b", MINUTE)).isTrue();
    }

    @Test
    void givenHeldKey_whenReleasedByANonHolder_thenNothingChanges() {
        leases.acquire("guarded", "a", MINUTE);

        leases.release("guarded", "b");

        assertThat(leases.holder("guarded")).map(LeasePort.Lease::owner).contains("a");
    }
}

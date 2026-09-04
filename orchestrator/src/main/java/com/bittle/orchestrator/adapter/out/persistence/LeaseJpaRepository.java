package com.bittle.orchestrator.adapter.out.persistence;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface LeaseJpaRepository extends JpaRepository<LeaseEntity, String> {

    @Modifying
    @Transactional
    @Query("update LeaseEntity l set l.holder = :holder, l.expiresAt = :until "
            + "where l.leaseKey = :key and (l.holder = :holder or l.expiresAt < :now)")
    int claim(@Param("key") String key, @Param("holder") String holder,
              @Param("now") Instant now, @Param("until") Instant until);

    @Modifying
    @Transactional
    @Query("update LeaseEntity l set l.expiresAt = :now "
            + "where l.leaseKey = :key and l.holder = :holder")
    int expire(@Param("key") String key, @Param("holder") String holder,
               @Param("now") Instant now);
}

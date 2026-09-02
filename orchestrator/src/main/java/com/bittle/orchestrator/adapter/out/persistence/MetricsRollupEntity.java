package com.bittle.orchestrator.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * One hourly usage-metrics snapshot per robot (plus one for the orchestrator
 * itself under robotId "orchestrator"). Kept permanently — hourly rows are
 * tiny and the totals are accounting data (see OBSERVABILITY_MIND_BRIEF §D.1).
 */
@Entity
@Table(name = "metrics_rollups")
public class MetricsRollupEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String robotId;

    @Column(nullable = false)
    private Instant hourStart;

    @Column(columnDefinition = "text", nullable = false)
    private String snapshotJson;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getRobotId() { return robotId; }
    public void setRobotId(String robotId) { this.robotId = robotId; }

    public Instant getHourStart() { return hourStart; }
    public void setHourStart(Instant hourStart) { this.hourStart = hourStart; }

    public String getSnapshotJson() { return snapshotJson; }
    public void setSnapshotJson(String snapshotJson) { this.snapshotJson = snapshotJson; }
}

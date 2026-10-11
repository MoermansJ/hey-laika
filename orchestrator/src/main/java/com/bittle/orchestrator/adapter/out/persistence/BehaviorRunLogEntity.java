package com.bittle.orchestrator.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

/**
 * Run-log row. The outcome evaluation is stored as flat, nullable
 * {@code outcome_*} columns on the same row (design §1: "appended to existing
 * run rows, not a new table"), so rows written before an evaluation exists, or
 * for non-agent runs, stay valid with those columns null. With
 * {@code ddl-auto: update} Hibernate only ever adds nullable columns here.
 * {@code outcomeEvaluatedAt} is the presence marker for an outcome.
 */
@Entity
@Table(name = "behavior_run_logs", indexes = {
        @Index(name = "idx_behavior_run_logs_robot_goal", columnList = "robotId, goal"),
        @Index(name = "idx_behavior_run_logs_robot_source", columnList = "robotId, source")})
public class BehaviorRunLogEntity {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String robotId;

    // Column is not called "timestamp": that is an SQL keyword in H2/PostgreSQL.
    @Column(name = "started_at", nullable = false)
    private Instant runTimestamp;

    private Instant completedAt;
    private String behaviorName;
    private String source;
    private Integer priority;

    @Column(columnDefinition = "text")
    private String causeJson;

    private Long executionTimeMs;
    private String preemptedBy;
    private String goal;

    @Column(columnDefinition = "text")
    private String sensorDeltaJson;

    private Boolean outcomeSuccess;
    private Double outcomeConfidence;

    @Column(columnDefinition = "text")
    private String outcomeReason;

    private String outcomeEvaluatorVersion;
    private Instant outcomeEvaluatedAt;

    private Instant createdAt;
    private Instant updatedAt;

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }

    public String getRobotId() { return robotId; }
    public void setRobotId(String robotId) { this.robotId = robotId; }

    public Instant getRunTimestamp() { return runTimestamp; }
    public void setRunTimestamp(Instant runTimestamp) { this.runTimestamp = runTimestamp; }

    public Instant getCompletedAt() { return completedAt; }
    public void setCompletedAt(Instant completedAt) { this.completedAt = completedAt; }

    public String getBehaviorName() { return behaviorName; }
    public void setBehaviorName(String behaviorName) { this.behaviorName = behaviorName; }

    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }

    public Integer getPriority() { return priority; }
    public void setPriority(Integer priority) { this.priority = priority; }

    public String getCauseJson() { return causeJson; }
    public void setCauseJson(String causeJson) { this.causeJson = causeJson; }

    public Long getExecutionTimeMs() { return executionTimeMs; }
    public void setExecutionTimeMs(Long executionTimeMs) { this.executionTimeMs = executionTimeMs; }

    public String getPreemptedBy() { return preemptedBy; }
    public void setPreemptedBy(String preemptedBy) { this.preemptedBy = preemptedBy; }

    public String getGoal() { return goal; }
    public void setGoal(String goal) { this.goal = goal; }

    public String getSensorDeltaJson() { return sensorDeltaJson; }
    public void setSensorDeltaJson(String sensorDeltaJson) { this.sensorDeltaJson = sensorDeltaJson; }

    public Boolean getOutcomeSuccess() { return outcomeSuccess; }
    public void setOutcomeSuccess(Boolean outcomeSuccess) { this.outcomeSuccess = outcomeSuccess; }

    public Double getOutcomeConfidence() { return outcomeConfidence; }
    public void setOutcomeConfidence(Double outcomeConfidence) { this.outcomeConfidence = outcomeConfidence; }

    public String getOutcomeReason() { return outcomeReason; }
    public void setOutcomeReason(String outcomeReason) { this.outcomeReason = outcomeReason; }

    public String getOutcomeEvaluatorVersion() { return outcomeEvaluatorVersion; }
    public void setOutcomeEvaluatorVersion(String outcomeEvaluatorVersion) {
        this.outcomeEvaluatorVersion = outcomeEvaluatorVersion;
    }

    public Instant getOutcomeEvaluatedAt() { return outcomeEvaluatedAt; }
    public void setOutcomeEvaluatedAt(Instant outcomeEvaluatedAt) { this.outcomeEvaluatedAt = outcomeEvaluatedAt; }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}

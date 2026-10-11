package com.bittle.orchestrator.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.UUID;

/**
 * Learned-pattern row. The ordered tool combination is stored as its canonical
 * JSON array text (e.g. {@code ["raise_right_paw","look_up"]}) so the design's
 * cache key {@code (robotId, goal, toolCombination)} is a plain, indexed and
 * unique column triple. The table is created by {@code ddl-auto: update}; it is
 * new, so no existing rows are affected.
 */
@Entity
@Table(name = "learned_patterns",
        uniqueConstraints = @UniqueConstraint(name = "uk_learned_patterns_robot_goal_combo",
                columnNames = {"robot_id", "goal", "tool_combination"}),
        indexes = {
                @Index(name = "idx_learned_patterns_robot_goal_rate",
                        columnList = "robot_id, goal, success_rate"),
                @Index(name = "idx_learned_patterns_robot_status", columnList = "robot_id, status")})
public class LearnedPatternEntity {

    @Id
    private UUID id;

    @Column(name = "robot_id", nullable = false)
    private String robotId;

    @Column(name = "goal", nullable = false)
    private String goal;

    @Column(name = "tool_combination", nullable = false, length = 2048)
    private String toolCombinationJson;

    @Column(nullable = false)
    private int attempts;

    @Column(nullable = false)
    private int successes;

    @Column(name = "success_rate", nullable = false)
    private double successRate;

    private Instant firstDiscovered;
    private Instant lastUsed;

    @Column(name = "status", nullable = false)
    private String status;

    private Instant createdAt;
    private Instant updatedAt;

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }

    public String getRobotId() { return robotId; }
    public void setRobotId(String robotId) { this.robotId = robotId; }

    public String getGoal() { return goal; }
    public void setGoal(String goal) { this.goal = goal; }

    public String getToolCombinationJson() { return toolCombinationJson; }
    public void setToolCombinationJson(String toolCombinationJson) {
        this.toolCombinationJson = toolCombinationJson;
    }

    public int getAttempts() { return attempts; }
    public void setAttempts(int attempts) { this.attempts = attempts; }

    public int getSuccesses() { return successes; }
    public void setSuccesses(int successes) { this.successes = successes; }

    public double getSuccessRate() { return successRate; }
    public void setSuccessRate(double successRate) { this.successRate = successRate; }

    public Instant getFirstDiscovered() { return firstDiscovered; }
    public void setFirstDiscovered(Instant firstDiscovered) { this.firstDiscovered = firstDiscovered; }

    public Instant getLastUsed() { return lastUsed; }
    public void setLastUsed(Instant lastUsed) { this.lastUsed = lastUsed; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}

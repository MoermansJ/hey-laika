package com.bittle.orchestrator.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "robot_modes")
public class RobotModeEntity {

    @Id
    @Column(name = "robot_id")
    private String robotId;

    private String mode;
    private Instant changedAt;
    private String changedBy;

    public String getRobotId() { return robotId; }
    public void setRobotId(String robotId) { this.robotId = robotId; }

    public String getMode() { return mode; }
    public void setMode(String mode) { this.mode = mode; }

    public Instant getChangedAt() { return changedAt; }
    public void setChangedAt(Instant changedAt) { this.changedAt = changedAt; }

    public String getChangedBy() { return changedBy; }
    public void setChangedBy(String changedBy) { this.changedBy = changedBy; }
}

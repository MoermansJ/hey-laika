package com.bittle.orchestrator.adapter.out.persistence;

import com.bittle.orchestrator.domain.robot.RobotIntroduction;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "robot_introductions")
public class RobotIntroductionEntity {

    @Id
    @Column(name = "robot_id")
    private String robotId;

    // Named explicitly: "text" is a type name in Postgres and reads badly as a
    // column. Length matches RobotIntroduction.MAX_CHARS.
    @Column(name = "introduction", length = RobotIntroduction.MAX_CHARS)
    private String introduction;

    private Instant updatedAt;
    private String updatedBy;

    public String getRobotId() { return robotId; }
    public void setRobotId(String robotId) { this.robotId = robotId; }

    public String getIntroduction() { return introduction; }
    public void setIntroduction(String introduction) { this.introduction = introduction; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }

    public String getUpdatedBy() { return updatedBy; }
    public void setUpdatedBy(String updatedBy) { this.updatedBy = updatedBy; }
}

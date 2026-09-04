package com.bittle.orchestrator.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "behavior_decisions",
        indexes = @Index(name = "idx_behavior_decisions_robot", columnList = "robotId, id"))
public class BehaviorDecisionEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String robotId;

    @Column(nullable = false)
    private Instant decidedAt;

    private String selectedAction;
    private String source;

    @Column(columnDefinition = "text")
    private String reasoning;

    private Boolean success;
    private Long actualDurationMs;

    @Column(columnDefinition = "text", nullable = false)
    private String stateJson;

    @Column(columnDefinition = "text", nullable = false)
    private String validActionsJson;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getRobotId() { return robotId; }
    public void setRobotId(String robotId) { this.robotId = robotId; }

    public Instant getDecidedAt() { return decidedAt; }
    public void setDecidedAt(Instant decidedAt) { this.decidedAt = decidedAt; }

    public String getSelectedAction() { return selectedAction; }
    public void setSelectedAction(String selectedAction) { this.selectedAction = selectedAction; }

    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }

    public String getReasoning() { return reasoning; }
    public void setReasoning(String reasoning) { this.reasoning = reasoning; }

    public Boolean getSuccess() { return success; }
    public void setSuccess(Boolean success) { this.success = success; }

    public Long getActualDurationMs() { return actualDurationMs; }
    public void setActualDurationMs(Long actualDurationMs) { this.actualDurationMs = actualDurationMs; }

    public String getStateJson() { return stateJson; }
    public void setStateJson(String stateJson) { this.stateJson = stateJson; }

    public String getValidActionsJson() { return validActionsJson; }
    public void setValidActionsJson(String validActionsJson) { this.validActionsJson = validActionsJson; }
}

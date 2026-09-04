package com.bittle.orchestrator.adapter.out.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "personality_states")
public class PersonalityStateEntity {

    @Id
    @Column(name = "robot_id")
    private String robotId;

    private double energy;
    private double happiness;
    private double boredom;
    private double curiosity;
    private double hunger;
    private double contentment;
    private String posture;
    private String lastAction;
    private Instant lastActionAt;
    private Instant lastInteractionAt;
    private long totalActions;
    private Instant updatedAt;

    public String getRobotId() { return robotId; }
    public void setRobotId(String robotId) { this.robotId = robotId; }

    public double getEnergy() { return energy; }
    public void setEnergy(double energy) { this.energy = energy; }

    public double getHappiness() { return happiness; }
    public void setHappiness(double happiness) { this.happiness = happiness; }

    public double getBoredom() { return boredom; }
    public void setBoredom(double boredom) { this.boredom = boredom; }

    public double getCuriosity() { return curiosity; }
    public void setCuriosity(double curiosity) { this.curiosity = curiosity; }

    public double getHunger() { return hunger; }
    public void setHunger(double hunger) { this.hunger = hunger; }

    public double getContentment() { return contentment; }
    public void setContentment(double contentment) { this.contentment = contentment; }

    public String getPosture() { return posture; }
    public void setPosture(String posture) { this.posture = posture; }

    public String getLastAction() { return lastAction; }
    public void setLastAction(String lastAction) { this.lastAction = lastAction; }

    public Instant getLastActionAt() { return lastActionAt; }
    public void setLastActionAt(Instant lastActionAt) { this.lastActionAt = lastActionAt; }

    public Instant getLastInteractionAt() { return lastInteractionAt; }
    public void setLastInteractionAt(Instant lastInteractionAt) { this.lastInteractionAt = lastInteractionAt; }

    public long getTotalActions() { return totalActions; }
    public void setTotalActions(long totalActions) { this.totalActions = totalActions; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}

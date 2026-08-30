package com.bittle.orchestrator.behavior;

import java.time.Instant;

/**
 * Mutable personality state of one robot. All personality dimensions are in
 * [0.0, 1.0]; {@link #clip()} is applied after every mutation by the
 * {@link PersonalityStateManager}. Not thread-safe on its own — the owning
 * behavior loop is the only writer.
 */
public class PersonalityState {

    private double energy = 0.6;
    private double happiness = 0.7;
    private double boredom = 0.4;
    private double curiosity = 0.5;
    private double hunger = 0.3;
    private double contentment = 0.6;

    private Posture posture = Posture.STANDING;
    private Action lastAction;
    private Instant lastActionAt;
    private Instant lastInteractionAt = Instant.now();
    private long totalActionsThisSession;

    public double energy() {
        return energy;
    }

    public double happiness() {
        return happiness;
    }

    public double boredom() {
        return boredom;
    }

    public double curiosity() {
        return curiosity;
    }

    public double hunger() {
        return hunger;
    }

    public double contentment() {
        return contentment;
    }

    public Posture posture() {
        return posture;
    }

    public Action lastAction() {
        return lastAction;
    }

    public Instant lastActionAt() {
        return lastActionAt;
    }

    public Instant lastInteractionAt() {
        return lastInteractionAt;
    }

    public long totalActionsThisSession() {
        return totalActionsThisSession;
    }

    void apply(PersonalityDelta delta) {
        energy += delta.energy();
        happiness += delta.happiness();
        boredom += delta.boredom();
        curiosity += delta.curiosity();
        hunger += delta.hunger();
        contentment += delta.contentment();
        clip();
    }

    void capBoredom(double max) {
        boredom = Math.min(boredom, max);
    }

    void driftContentmentTowardNeutral(double rate) {
        contentment += (0.5 - contentment) * rate;
        clip();
    }

    void setPosture(Posture posture) {
        this.posture = posture;
    }

    void recordAction(Action action, Instant at) {
        this.lastAction = action;
        this.lastActionAt = at;
        this.totalActionsThisSession++;
    }

    void recordInteraction(Instant at) {
        this.lastInteractionAt = at;
    }

    private void clip() {
        energy = clip(energy);
        happiness = clip(happiness);
        boredom = clip(boredom);
        curiosity = clip(curiosity);
        hunger = clip(hunger);
        contentment = clip(contentment);
    }

    private static double clip(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }

    public Snapshot snapshot(String robotId) {
        return new Snapshot(robotId, energy, happiness, boredom, curiosity, hunger,
                contentment, posture,
                lastAction == null ? null : lastAction.actionId(),
                lastActionAt, lastInteractionAt, totalActionsThisSession);
    }

    /** Immutable view served over REST and STOMP. */
    public record Snapshot(String robotId, double energy, double happiness,
                           double boredom, double curiosity, double hunger,
                           double contentment, Posture posture, String lastAction,
                           Instant lastActionAt, Instant lastInteractionAt,
                           long totalActionsThisSession) {
    }
}

package com.bittle.orchestrator.domain.behavior;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/**
 * Hand-authored voice/GUI metadata per {@link Action}. There is no external
 * store this is read from — this class IS the store.
 */
public final class ActionCatalog {

    private static final Map<Action, ActionMetadata> METADATA = build();

    private ActionCatalog() {
    }

    public static ActionMetadata metadataFor(Action action) {
        return METADATA.get(action);
    }

    private static Map<Action, ActionMetadata> build() {
        Map<Action, ActionMetadata> catalog = new EnumMap<>(Action.class);
        catalog.put(Action.WALK_SLOW, new ActionMetadata(
                List.of("walk", "walk slow", "go for a walk"),
                "Walks forward at a slow, relaxed pace", List.of("locomotion")));
        catalog.put(Action.WALK_FAST, new ActionMetadata(
                List.of("run", "walk fast", "hurry"),
                "Walks forward at a brisk pace", List.of("locomotion")));
        catalog.put(Action.STAND_UP, new ActionMetadata(
                List.of("stand up", "get up", "stand"),
                "Rises to a standing posture", List.of("posture")));
        catalog.put(Action.SIT_DOWN, new ActionMetadata(
                List.of("sit", "sit down", "take a seat"),
                "Sits down from standing", List.of("posture")));
        catalog.put(Action.LIE_DOWN, new ActionMetadata(
                List.of("lie down", "lay down", "down"),
                "Lies down from standing or sitting", List.of("posture")));
        catalog.put(Action.LOOK_LEFT, new ActionMetadata(
                List.of("look left"),
                "Turns its head to look left", List.of("look")));
        catalog.put(Action.LOOK_RIGHT, new ActionMetadata(
                List.of("look right"),
                "Turns its head to look right", List.of("look")));
        catalog.put(Action.LOOK_UP, new ActionMetadata(
                List.of("look up"),
                "Tilts its head to look up", List.of("look")));
        catalog.put(Action.LOOK_AROUND_LOW, new ActionMetadata(
                List.of("look around", "check surroundings"),
                "Looks around while sitting", List.of("look")));
        catalog.put(Action.LOOK_AROUND_SLOW, new ActionMetadata(
                List.of("look around slowly", "survey the room"),
                "Looks around slowly while standing", List.of("look")));
        catalog.put(Action.STRETCH, new ActionMetadata(
                List.of("stretch"),
                "Stretches its body", List.of("posture")));
        catalog.put(Action.PLAY_BOW, new ActionMetadata(
                List.of("play bow", "bow", "let's play"),
                "Performs a playful bow", List.of("trick")));
        catalog.put(Action.BACKFLIP, new ActionMetadata(
                List.of("backflip", "flip"),
                "Performs a backflip", List.of("trick")));
        catalog.put(Action.SPIN, new ActionMetadata(
                List.of("spin", "spin around", "turn around"),
                "Spins in place", List.of("trick")));
        catalog.put(Action.IDLE_CALM, new ActionMetadata(
                List.of("relax", "settle down"),
                "Settles into a calm idle state", List.of("sleep")));
        catalog.put(Action.SLEEP, new ActionMetadata(
                List.of("sleep", "go to sleep", "nap"),
                "Falls asleep while lying down", List.of("sleep")));
        catalog.put(Action.WAKE_UP, new ActionMetadata(
                List.of("wake up", "wake"),
                "Wakes up from sleep", List.of("sleep")));
        catalog.put(Action.SEEK_ATTENTION, new ActionMetadata(
                List.of("come here", "pay attention to me"),
                "Seeks the owner's attention", List.of("social")));
        return Map.copyOf(catalog);
    }
}

package com.bittle.orchestrator.domain.behavior;

import java.util.Collections;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Which tools the agent may call in each operating mode (AGENT-14, design §3.3
 * {@code getAvailableTools}). The lists are fixed, so they are built once per mode
 * and handed out as immutable lists.
 * <ul>
 *   <li>STATIONARY — look left/right/upward, tilt head, bark, sit, stand (no walking)</li>
 *   <li>ROAMING — every tool</li>
 *   <li>FRUITFLY — none (the connectome drives the body)</li>
 *   <li>PHONE — none (not covered by the design; no agent motion until it is)</li>
 * </ul>
 */
public final class AgentToolCatalog {

    public static final String POSTURAL = "postural";
    public static final String LOCOMOTIVE = "locomotive";
    public static final String VOCAL = "vocal";

    private static final ToolDescriptor LOOK_LEFT =
            new ToolDescriptor("look_left", "Face left", POSTURAL);
    private static final ToolDescriptor LOOK_RIGHT =
            new ToolDescriptor("look_right", "Face right", POSTURAL);
    private static final ToolDescriptor LOOK_UPWARD =
            new ToolDescriptor("look_upward", "Face upward", POSTURAL);
    private static final ToolDescriptor TILT_HEAD =
            new ToolDescriptor("tilt_head", "Tilt head to one side", POSTURAL);
    private static final ToolDescriptor BARK = new ToolDescriptor("bark", "Bark once", VOCAL);
    private static final ToolDescriptor SIT = new ToolDescriptor("sit", "Sit down", POSTURAL);
    private static final ToolDescriptor STAND = new ToolDescriptor("stand", "Stand up", POSTURAL);
    private static final ToolDescriptor MOVE_FORWARD =
            new ToolDescriptor("move_forward", "Walk forward", LOCOMOTIVE);
    private static final ToolDescriptor MOVE_BACKWARD =
            new ToolDescriptor("move_backward", "Walk backward", LOCOMOTIVE);
    private static final ToolDescriptor TURN_LEFT =
            new ToolDescriptor("turn_left", "Rotate left", LOCOMOTIVE);
    private static final ToolDescriptor TURN_RIGHT =
            new ToolDescriptor("turn_right", "Rotate right", LOCOMOTIVE);

    private static final Map<OperatingMode, List<ToolDescriptor>> BY_MODE = build();
    private static final Map<OperatingMode, Set<String>> NAMES_BY_MODE = names();

    private AgentToolCatalog() {
    }

    /** The tools available in the mode, in a stable order; empty when none. */
    public static List<ToolDescriptor> toolsFor(OperatingMode mode) {
        return mode == null ? List.of() : BY_MODE.getOrDefault(mode, List.of());
    }

    /** True when the named tool may be called in the mode. */
    public static boolean isAllowed(OperatingMode mode, String toolName) {
        return mode != null && toolName != null
                && NAMES_BY_MODE.getOrDefault(mode, Set.of()).contains(toolName);
    }

    private static Map<OperatingMode, List<ToolDescriptor>> build() {
        Map<OperatingMode, List<ToolDescriptor>> byMode = new EnumMap<>(OperatingMode.class);
        byMode.put(OperatingMode.STATIONARY,
                List.of(LOOK_LEFT, LOOK_RIGHT, LOOK_UPWARD, TILT_HEAD, BARK, SIT, STAND));
        byMode.put(OperatingMode.ROAMING, List.of(MOVE_FORWARD, MOVE_BACKWARD, TURN_LEFT,
                TURN_RIGHT, LOOK_LEFT, LOOK_RIGHT, LOOK_UPWARD, TILT_HEAD, BARK, SIT, STAND));
        byMode.put(OperatingMode.FRUITFLY, List.of());
        byMode.put(OperatingMode.PHONE, List.of());
        return Collections.unmodifiableMap(byMode);
    }

    private static Map<OperatingMode, Set<String>> names() {
        Map<OperatingMode, Set<String>> names = new EnumMap<>(OperatingMode.class);
        BY_MODE.forEach((mode, tools) -> names.put(mode,
                tools.stream().map(ToolDescriptor::name).collect(Collectors.toUnmodifiableSet())));
        return Collections.unmodifiableMap(names);
    }
}

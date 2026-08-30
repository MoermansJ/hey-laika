package com.bittle.orchestrator.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.dto.Dtos.ServoJoint;
import com.bittle.orchestrator.dto.Dtos.ServoMoveResult;
import com.bittle.orchestrator.dto.Dtos.ServoState;
import com.bittle.orchestrator.exception.RobotNotFoundException;
import com.bittle.orchestrator.fleet.FleetManager;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(RobotController.class)
class RobotControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private FleetManager fleetManager;

    @MockitoBean
    private com.bittle.orchestrator.behavior.BehaviorService behaviorService;

    private void loopRunning(String robotId, boolean running) {
        var loop = mock(com.bittle.orchestrator.behavior.RobotBehaviorLoop.class);
        when(loop.isRunning()).thenReturn(running);
        when(behaviorService.loop(robotId)).thenReturn(loop);
    }

    @Test
    void executeActionIsProxiedWhenLoopStopped() throws Exception {
        loopRunning("bittle-1", false);
        var agent = mock(RobotAgent.class);
        when(agent.executeAction(any())).thenReturn(new com.bittle.orchestrator.dto.Dtos
                .ActionResult("bittle-1", "sit_down", true, 1500L, "executed"));
        when(fleetManager.get("bittle-1")).thenReturn(agent);

        mvc.perform(post("/api/robots/bittle-1/execute_action")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"sit_down\",\"durationMs\":1500,\"sequenceId\":1}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true));
    }

    @Test
    void executeActionIs409WhileLoopRuns() throws Exception {
        loopRunning("bittle-1", true);

        mvc.perform(post("/api/robots/bittle-1/execute_action")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"action\":\"sit_down\",\"durationMs\":1500,\"sequenceId\":1}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("behavior_loop_running"));
    }

    @Test
    void statusIsProxiedFromAgent() throws Exception {
        var agent = mock(RobotAgent.class);
        when(agent.status())
                .thenReturn(new RobotStatus("bittle-1", true, "mock", "kbalance", 5, false,
                        "happy", 87.5, "strong", 120L));
        when(fleetManager.get("bittle-1")).thenReturn(agent);

        mvc.perform(get("/api/robots/bittle-1/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.robotId").value("bittle-1"))
                .andExpect(jsonPath("$.connected").value(true))
                .andExpect(jsonPath("$.mood").value("happy"));
    }

    @Test
    void capabilitiesArePassedThroughUntyped() throws Exception {
        var agent = mock(RobotAgent.class);
        when(agent.capabilities()).thenReturn(Map.of(
                "robotId", "bittle-1",
                "schema", Map.of("servos", List.of(Map.of("index", 0, "min", -90)))));
        when(fleetManager.get("bittle-1")).thenReturn(agent);

        mvc.perform(get("/api/robots/bittle-1/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schema.servos[0].index").value(0))
                .andExpect(jsonPath("$.schema.servos[0].min").value(-90));
    }

    @Test
    void servoStateIsProxied() throws Exception {
        var agent = mock(RobotAgent.class);
        when(agent.servoState()).thenReturn(new ServoState("bittle-1", true,
                "2026-08-30T12:00:00Z", List.of(new ServoJoint(0, 30))));
        when(fleetManager.get("bittle-1")).thenReturn(agent);

        mvc.perform(get("/api/robots/bittle-1/servo"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.joints[0].angle").value(30));
    }

    @Test
    void servoMoveIsProxied() throws Exception {
        var agent = mock(RobotAgent.class);
        when(agent.moveServos(any())).thenReturn(new ServoMoveResult("bittle-1",
                true, false, "Moved 1 joint(s)", List.of(new ServoJoint(0, 25))));
        when(fleetManager.get("bittle-1")).thenReturn(agent);

        mvc.perform(post("/api/robots/bittle-1/servo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"joints\":[{\"index\":0,\"angle\":25}]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.movedJoints[0].index").value(0));
    }

    @Test
    void unknownRobotIs404() throws Exception {
        when(fleetManager.get("ghost")).thenThrow(new RobotNotFoundException("ghost"));

        mvc.perform(get("/api/robots/ghost/status"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("robot_not_found"));
    }
}

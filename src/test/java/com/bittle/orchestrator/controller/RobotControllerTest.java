package com.bittle.orchestrator.controller;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bittle.orchestrator.agent.RobotAgent;
import com.bittle.orchestrator.dto.Dtos.RobotStatus;
import com.bittle.orchestrator.exception.RobotNotFoundException;
import com.bittle.orchestrator.fleet.FleetManager;
import org.junit.jupiter.api.Test;
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

    @Test
    void statusIsProxiedFromAgent() throws Exception {
        var agent = mock(RobotAgent.class);
        when(agent.status())
                .thenReturn(new RobotStatus("bittle-1", true, "mock", "kbalance", 5, false, "happy"));
        when(fleetManager.get("bittle-1")).thenReturn(agent);

        mvc.perform(get("/api/robots/bittle-1/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.robotId").value("bittle-1"))
                .andExpect(jsonPath("$.connected").value(true))
                .andExpect(jsonPath("$.mood").value("happy"));
    }

    @Test
    void unknownRobotIs404() throws Exception {
        when(fleetManager.get("ghost")).thenThrow(new RobotNotFoundException("ghost"));

        mvc.perform(get("/api/robots/ghost/status"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("robot_not_found"));
    }
}

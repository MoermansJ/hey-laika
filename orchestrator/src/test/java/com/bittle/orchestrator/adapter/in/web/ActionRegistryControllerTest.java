package com.bittle.orchestrator.adapter.in.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.OrchestratorMetricsPort;
import com.bittle.orchestrator.application.usecase.GetActionRegistryEntryUseCase;
import com.bittle.orchestrator.application.usecase.GetActionRegistryUseCase;
import com.bittle.orchestrator.domain.behavior.ActionNotFoundException;
import com.bittle.orchestrator.domain.behavior.ActionRegistryEntry;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.assertj.MockMvcTester;

@WebMvcTest(ActionRegistryController.class)
@MockitoBean(types = {GetActionRegistryUseCase.class, GetActionRegistryEntryUseCase.class,
        OrchestratorMetricsPort.class})
class ActionRegistryControllerTest {

    @Autowired
    private MockMvcTester mvc;

    @Autowired
    private GetActionRegistryUseCase getRegistry;

    @Autowired
    private GetActionRegistryEntryUseCase getRegistryEntry;

    @Test
    void whenActionsRequested_thenRegistryListIsReturned() {
        when(getRegistry.execute()).thenReturn(List.of(
                new ActionRegistryEntry("sit_down", List.of("sit", "sit down"),
                        "Sits down from standing", List.of("posture"))));

        var result = mvc.get().uri("/api/actions").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().isLenientlyEqualTo("""
                        {"actions": [{"actionName": "sit_down", "aliases": ["sit", "sit down"]}]}
                        """);
    }

    @Test
    void givenKnownActionName_whenRequested_thenEntryIsReturned() {
        when(getRegistryEntry.execute("sit_down")).thenReturn(
                new ActionRegistryEntry("sit_down", List.of("sit"),
                        "Sits down from standing", List.of("posture")));

        var result = mvc.get().uri("/api/actions/sit_down").exchange();

        assertThat(result).hasStatusOk()
                .bodyJson().extractingPath("$.description").isEqualTo("Sits down from standing");
    }

    @Test
    void givenUnknownActionName_whenRequested_thenNotFoundIsReturned() {
        when(getRegistryEntry.execute("fly")).thenThrow(new ActionNotFoundException("fly"));

        var result = mvc.get().uri("/api/actions/fly").exchange();

        assertThat(result).hasStatus(HttpStatus.NOT_FOUND)
                .bodyJson().extractingPath("$.error").isEqualTo("action_not_found");
    }
}

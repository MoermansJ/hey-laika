package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.bittle.orchestrator.domain.behavior.ActionNotFoundException;
import org.junit.jupiter.api.Test;

class GetActionRegistryEntryUseCaseTest {

    private final GetActionRegistryEntryUseCase useCase = new GetActionRegistryEntryUseCase();

    @Test
    void givenKnownActionName_whenExecuted_thenEntryMatchesTheAction() {
        var entry = useCase.execute("sit_down");

        assertThat(entry.actionName()).isEqualTo("sit_down");
        assertThat(entry.aliases()).contains("sit");
    }

    @Test
    void givenKnownActionNameInDifferentCase_whenExecuted_thenLookupIsCaseInsensitive() {
        var entry = useCase.execute("SIT_DOWN");

        assertThat(entry.actionName()).isEqualTo("sit_down");
    }

    @Test
    void givenUnknownActionName_whenExecuted_thenActionNotFoundExceptionIsThrown() {
        assertThatThrownBy(() -> useCase.execute("fly"))
                .isInstanceOf(ActionNotFoundException.class);
    }
}

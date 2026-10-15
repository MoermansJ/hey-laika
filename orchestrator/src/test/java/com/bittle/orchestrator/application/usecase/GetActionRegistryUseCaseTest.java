package com.bittle.orchestrator.application.usecase;

import static org.assertj.core.api.Assertions.assertThat;

import com.bittle.orchestrator.domain.behavior.Action;
import org.junit.jupiter.api.Test;

class GetActionRegistryUseCaseTest {

    private final GetActionRegistryUseCase useCase = new GetActionRegistryUseCase();

    @Test
    void whenExecuted_thenEveryActionHasNonEmptyMetadata() {
        var entries = useCase.execute();

        assertThat(entries).hasSize(Action.values().length);
        assertThat(entries).allSatisfy(entry -> {
            assertThat(entry.actionName()).isNotBlank();
            assertThat(entry.description()).isNotBlank();
            assertThat(entry.aliases()).isNotEmpty();
            assertThat(entry.tags()).isNotEmpty();
        });
    }
}

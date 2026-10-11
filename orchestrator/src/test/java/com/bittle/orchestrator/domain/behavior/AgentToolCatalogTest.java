package com.bittle.orchestrator.domain.behavior;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class AgentToolCatalogTest {

    @Test
    void givenStationary_whenToolsListed_thenOnlyNonWalkingToolsFromTheTicket() {
        assertThat(AgentToolCatalog.toolsFor(OperatingMode.STATIONARY))
                .extracting(ToolDescriptor::name)
                .containsExactly("look_left", "look_right", "look_upward", "tilt_head", "bark",
                        "sit", "stand");
        assertThat(AgentToolCatalog.toolsFor(OperatingMode.STATIONARY))
                .extracting(ToolDescriptor::category)
                .doesNotContain(AgentToolCatalog.LOCOMOTIVE);
    }

    @Test
    void givenRoaming_whenToolsListed_thenEveryToolIncludingWalking() {
        var roaming = AgentToolCatalog.toolsFor(OperatingMode.ROAMING);

        assertThat(roaming).containsAll(AgentToolCatalog.toolsFor(OperatingMode.STATIONARY));
        assertThat(roaming).extracting(ToolDescriptor::name)
                .contains("move_forward", "move_backward", "turn_left", "turn_right");
        assertThat(roaming).extracting(ToolDescriptor::name).doesNotHaveDuplicates();
    }

    @Test
    void givenFruitflyOrPhone_whenToolsListed_thenNone() {
        assertThat(AgentToolCatalog.toolsFor(OperatingMode.FRUITFLY)).isEmpty();
        assertThat(AgentToolCatalog.toolsFor(OperatingMode.PHONE)).isEmpty();
        assertThat(AgentToolCatalog.toolsFor(null)).isEmpty();
    }

    @Test
    void givenModes_whenToolChecked_thenAllowedMatchesTheLists() {
        assertThat(AgentToolCatalog.isAllowed(OperatingMode.STATIONARY, "bark")).isTrue();
        assertThat(AgentToolCatalog.isAllowed(OperatingMode.STATIONARY, "move_forward")).isFalse();
        assertThat(AgentToolCatalog.isAllowed(OperatingMode.ROAMING, "move_forward")).isTrue();
        assertThat(AgentToolCatalog.isAllowed(OperatingMode.FRUITFLY, "bark")).isFalse();
        assertThat(AgentToolCatalog.isAllowed(OperatingMode.ROAMING, null)).isFalse();
        assertThat(AgentToolCatalog.isAllowed(null, "bark")).isFalse();
    }

    @Test
    void givenCachedList_whenModified_thenRejected() {
        var tools = AgentToolCatalog.toolsFor(OperatingMode.ROAMING);

        assertThat(AgentToolCatalog.toolsFor(OperatingMode.ROAMING)).isSameAs(tools);
        assertThatThrownBy(tools::clear).isInstanceOf(UnsupportedOperationException.class);
    }
}

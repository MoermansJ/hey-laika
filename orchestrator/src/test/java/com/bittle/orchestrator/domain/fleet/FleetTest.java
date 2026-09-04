package com.bittle.orchestrator.domain.fleet;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;

class FleetTest {

    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://localhost:15001");

    @Test
    void givenEmptyFleet_whenUnknownRobotRequested_thenRobotNotFoundIsThrown() {
        var fleet = new Fleet(List.of());

        assertThatThrownBy(() -> fleet.get("ghost")).isInstanceOf(RobotNotFoundException.class);
        assertThat(fleet.isEmpty()).isTrue();
    }

    @Test
    void givenConfiguredRobot_whenRequestedById_thenTheSameRobotIsReturned() {
        var fleet = new Fleet(List.of(LAIKA));

        assertThat(fleet.get("bittle-1")).isSameAs(LAIKA);
        assertThat(fleet.all()).containsExactly(LAIKA);
    }

    @Test
    void givenDuplicateIds_whenConstructed_thenItIsRejected() {
        assertThatThrownBy(() -> new Fleet(List.of(LAIKA, LAIKA)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

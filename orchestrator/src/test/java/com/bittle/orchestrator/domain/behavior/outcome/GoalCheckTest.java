package com.bittle.orchestrator.domain.behavior.outcome;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class GoalCheckTest {

    @Test
    void givenConfidenceOutsideRange_whenCreated_thenClamped() {
        assertThat(GoalCheck.succeeded(1.7, "x").confidence()).isEqualTo(1.0);
        assertThat(GoalCheck.failed(-0.3, "x").confidence()).isZero();
        assertThat(new GoalCheck(true, Double.NaN, "x").confidence()).isZero();
    }

    @Test
    void givenFactories_whenCreated_thenSuccessFlagMatches() {
        assertThat(GoalCheck.succeeded(0.5, "ok").success()).isTrue();
        assertThat(GoalCheck.failed(0.5, "no").success()).isFalse();
        var undetermined = GoalCheck.undetermined("no data");
        assertThat(undetermined.success()).isNull();
        assertThat(undetermined.confidence()).isZero();
        assertThat(undetermined.reason()).isEqualTo("no data");
        assertThat(new GoalCheck(true, 1.0, null).reason()).isEmpty();
    }

    @Test
    void givenSnapshot_whenFrameRead_thenItIsADefensiveCopy() {
        byte[] frame = {1, 2, 3};
        var snapshot = new SensorSnapshot(Instant.EPOCH, frame, null, null, null);
        frame[0] = 9;
        snapshot.cameraFrame()[1] = 9;

        assertThat(snapshot.cameraFrame()).containsExactly(new byte[] {1, 2, 3});
        assertThat(snapshot.hasCameraFrame()).isTrue();
        assertThat(SensorSnapshot.empty(Instant.EPOCH).hasCameraFrame()).isFalse();
        assertThat(SensorSnapshot.empty(Instant.EPOCH).odometryPosition()).isNull();
    }
}

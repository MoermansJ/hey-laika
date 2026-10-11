package com.bittle.orchestrator.domain.behavior.outcome;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot.Imu;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot.Odometry;
import com.bittle.orchestrator.domain.behavior.outcome.SensorSnapshot.Point;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class GoalOutcomeCheckersTest {

    private static final Instant T0 = Instant.parse("2026-10-11T21:30:00Z");
    private static final OutcomeThresholds DEFAULTS = OutcomeThresholds.defaults();

    // ---- look_upward / look_left / look_right ---------------------------------

    @Test
    void givenCentroidMovedUp_whenLookUpwardChecked_thenSuccessWithScaledConfidence() {
        var check = new LookUpwardChecker(DEFAULTS).evaluate(
                centroid(320, 300), centroid(320, 240));

        assertThat(check.success()).isTrue();
        assertThat(check.confidence()).isCloseTo(0.6, within(1e-9));
        assertThat(check.reason()).contains("60 px upward").contains("threshold: 30 px");
    }

    @Test
    void givenCentroidBarelyMoved_whenLookUpwardChecked_thenFailure() {
        var check = new LookUpwardChecker(DEFAULTS).evaluate(
                centroid(320, 300), centroid(320, 290));

        assertThat(check.success()).isFalse();
        assertThat(check.confidence()).isCloseTo(1.0 - 10.0 / 30.0, within(1e-9));
    }

    @Test
    void givenCentroidMovedDown_whenLookUpwardChecked_thenConfidentFailure() {
        var check = new LookUpwardChecker(DEFAULTS).evaluate(
                centroid(320, 240), centroid(320, 300));

        assertThat(check.success()).isFalse();
        assertThat(check.confidence()).isEqualTo(1.0);
        assertThat(check.reason()).contains("the other way");
    }

    @Test
    void givenNoCentroidButImu_whenLookUpwardChecked_thenPitchDecides() {
        var check = new LookUpwardChecker(DEFAULTS).evaluate(imu(0, 0, 0), imu(20, 0, 0));

        assertThat(check.success()).isTrue();
        assertThat(check.reason()).contains("IMU");
    }

    @Test
    void givenNoCameraOrImu_whenLookChecked_thenUndetermined() {
        for (var checker : List.<GoalOutcomeChecker>of(new LookUpwardChecker(DEFAULTS),
                new LookLeftChecker(DEFAULTS), new LookRightChecker(DEFAULTS))) {
            var check = checker.evaluate(SensorSnapshot.empty(T0), SensorSnapshot.empty(T0));
            assertThat(check.success()).as(checker.goal()).isNull();
            assertThat(check.confidence()).isZero();
        }
    }

    @Test
    void givenCentroidMovedLeft_whenLeftAndRightChecked_thenOnlyLeftSucceeds() {
        var before = centroid(320, 240);
        var after = centroid(250, 240);

        assertThat(new LookLeftChecker(DEFAULTS).evaluate(before, after).success()).isTrue();
        assertThat(new LookRightChecker(DEFAULTS).evaluate(before, after).success()).isFalse();
        assertThat(new LookRightChecker(DEFAULTS).evaluate(after, before).success()).isTrue();
    }

    @Test
    void givenYawAcrossTheWrap_whenLeftAndRightChecked_thenShortestTurnIsUsed() {
        // 350 deg -> 15 deg is a 25 deg turn to the left (counter-clockwise).
        var before = imu(0, 0, 350);
        var after = imu(0, 0, 15);

        assertThat(new LookLeftChecker(DEFAULTS).evaluate(before, after).success()).isTrue();
        assertThat(new LookRightChecker(DEFAULTS).evaluate(before, after).success()).isFalse();
    }

    // ---- move_forward -------------------------------------------------------

    @Test
    void givenMovedSixCentimetresAhead_whenMoveForwardChecked_thenSuccess() {
        var check = new MoveForwardChecker(DEFAULTS).evaluate(odometry(0, 0, 0),
                odometry(6, 0, 0));

        assertThat(check.success()).isTrue();
        assertThat(check.confidence()).isCloseTo(0.3, within(1e-9));
        assertThat(check.reason()).isEqualTo("Moved forward 6.0 cm (threshold: 5.0 cm)");
    }

    @Test
    void givenHeadingNorth_whenMovedAlongY_thenThatCountsAsForward() {
        var check = new MoveForwardChecker(DEFAULTS).evaluate(odometry(10, 10, 90),
                odometry(10, 40, 90));

        assertThat(check.success()).isTrue();
        assertThat(check.confidence()).isCloseTo(1.0, within(1e-9));
    }

    @Test
    void givenSidewaysOrBackwards_whenMoveForwardChecked_thenFailure() {
        var checker = new MoveForwardChecker(DEFAULTS);

        assertThat(checker.evaluate(odometry(0, 0, 0), odometry(0, 30, 0)).success()).isFalse();
        var backwards = checker.evaluate(odometry(0, 0, 0), odometry(-10, 0, 0));
        assertThat(backwards.success()).isFalse();
        assertThat(backwards.confidence()).isEqualTo(1.0);
    }

    @Test
    void givenMissingOdometry_whenMoveForwardChecked_thenUndetermined() {
        assertThat(new MoveForwardChecker(DEFAULTS)
                .evaluate(SensorSnapshot.empty(T0), odometry(6, 0, 0)).success()).isNull();
    }

    // ---- listen_to_sound ----------------------------------------------------

    @Test
    void givenAmplitudeRose_whenListenChecked_thenSuccess() {
        var check = new ListenToSoundChecker(DEFAULTS).evaluate(audio(0.1, null),
                audio(0.4, null));

        assertThat(check.success()).isTrue();
        assertThat(check.confidence()).isCloseTo(1.0, within(1e-9));
        assertThat(check.reason()).contains("increased by 0.30");
    }

    @Test
    void givenAmplitudeFlat_whenListenChecked_thenFailure() {
        var check = new ListenToSoundChecker(DEFAULTS).evaluate(audio(0.2, null),
                audio(0.22, null));

        assertThat(check.success()).isFalse();
    }

    @Test
    void givenMissingAudio_whenListenChecked_thenUndetermined() {
        assertThat(new ListenToSoundChecker(DEFAULTS)
                .evaluate(audio(0.2, null), SensorSnapshot.empty(T0)).success()).isNull();
    }

    // ---- bark ---------------------------------------------------------------

    @Test
    void givenLoudPeakInBarkBand_whenBarkChecked_thenSuccess() {
        var check = new BarkChecker(DEFAULTS).evaluate(audio(0.05, null), audio(0.45, 800.0));

        assertThat(check.success()).isTrue();
        assertThat(check.confidence()).isCloseTo(0.75, within(1e-9));
        assertThat(check.reason()).contains("800 Hz");
    }

    @Test
    void givenLoudPeakWithoutSpectrum_whenBarkChecked_thenAmplitudeDecides() {
        assertThat(new BarkChecker(DEFAULTS).evaluate(audio(0.05, null), audio(0.5, null))
                .success()).isTrue();
    }

    @Test
    void givenLoudPeakOutsideBarkBand_whenBarkChecked_thenFailure() {
        var check = new BarkChecker(DEFAULTS).evaluate(audio(0.05, null), audio(0.6, 6000.0));

        assertThat(check.success()).isFalse();
        assertThat(check.reason()).contains("outside the bark band");
    }

    @Test
    void givenQuiet_whenBarkChecked_thenFailure() {
        assertThat(new BarkChecker(DEFAULTS).evaluate(audio(0.05, null), audio(0.1, 800.0))
                .success()).isFalse();
    }

    @Test
    void givenNoAudioAfter_whenBarkChecked_thenUndetermined() {
        assertThat(new BarkChecker(DEFAULTS).evaluate(audio(0.05, null),
                SensorSnapshot.empty(T0)).success()).isNull();
    }

    // ---- tilt_head ----------------------------------------------------------

    @Test
    void givenRollChangedEitherWay_whenTiltHeadChecked_thenSuccess() {
        var checker = new TiltHeadChecker(DEFAULTS);

        var right = checker.evaluate(imu(0, 0, 0), imu(0, 15, 0));
        assertThat(right.success()).isTrue();
        assertThat(right.confidence()).isCloseTo(0.5, within(1e-9));
        assertThat(right.reason()).contains("right");
        assertThat(checker.evaluate(imu(0, 0, 0), imu(0, -15, 0)).success()).isTrue();
    }

    @Test
    void givenRollBarelyChanged_whenTiltHeadChecked_thenFailure() {
        assertThat(new TiltHeadChecker(DEFAULTS).evaluate(imu(0, 0, 0), imu(0, 3, 0)).success())
                .isFalse();
    }

    @Test
    void givenNoImu_whenTiltHeadChecked_thenUndetermined() {
        assertThat(new TiltHeadChecker(DEFAULTS).evaluate(SensorSnapshot.empty(T0),
                imu(0, 15, 0)).success()).isNull();
    }

    // ---- configuration ------------------------------------------------------

    @Test
    void givenCustomThreshold_whenChecked_thenItIsUsed() {
        var strict = new OutcomeThresholds(30, 100, 10, 30, 10, 20, 0.1, 0.3, 0.3, 0.6, 250,
                2000, 10, 30);

        assertThat(new MoveForwardChecker(strict).evaluate(odometry(0, 0, 0), odometry(6, 0, 0))
                .success()).isFalse();
    }

    @Test
    void givenInvalidThresholds_whenCreated_thenRejected() {
        assertThatThrownBy(() -> new OutcomeThresholds(0, 100, 10, 30, 5, 20, 0.1, 0.3, 0.3,
                0.6, 250, 2000, 10, 30)).isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("lookCentroidPx");
        assertThatThrownBy(() -> new OutcomeThresholds(30, 100, 10, 30, 5, 20, 0.1, 0.3, 0.3,
                0.6, 2000, 250, 10, 30)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void givenCheckers_whenGoalsRead_thenTheyMatchTheDesignGoalNames() {
        assertThat(List.of(new LookUpwardChecker(DEFAULTS), new LookLeftChecker(DEFAULTS),
                        new LookRightChecker(DEFAULTS), new MoveForwardChecker(DEFAULTS),
                        new ListenToSoundChecker(DEFAULTS), new BarkChecker(DEFAULTS),
                        new TiltHeadChecker(DEFAULTS)))
                .extracting(GoalOutcomeChecker::goal)
                .containsExactly("look_upward", "look_left", "look_right", "move_forward",
                        "listen_to_sound", "bark", "tilt_head");
    }

    @Test
    void givenAngles_whenDeltaComputed_thenItIsTheShortestSignedTurn() {
        assertThat(Verdicts.angleDelta(350, 15)).isEqualTo(25.0);
        assertThat(Verdicts.angleDelta(15, 350)).isEqualTo(-25.0);
        assertThat(Verdicts.angleDelta(0, 180)).isEqualTo(180.0);
        assertThat(Verdicts.angleDelta(10, 10)).isZero();
    }

    private static SensorSnapshot centroid(double x, double y) {
        return new SensorSnapshot(T0, null, null, null, null, new Point(x, y), null);
    }

    private static SensorSnapshot imu(double pitch, double roll, double yaw) {
        return new SensorSnapshot(T0, null, null, null, new Imu(pitch, roll, yaw));
    }

    private static SensorSnapshot odometry(double x, double y, double heading) {
        return new SensorSnapshot(T0, null, new Odometry(x, y, heading), null, null);
    }

    private static SensorSnapshot audio(double peak, Double hz) {
        return new SensorSnapshot(T0, null, null, peak, null, null, hz);
    }
}

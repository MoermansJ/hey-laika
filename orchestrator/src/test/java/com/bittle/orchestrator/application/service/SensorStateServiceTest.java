package com.bittle.orchestrator.application.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.bittle.orchestrator.application.port.out.AdapterErrorException;
import com.bittle.orchestrator.application.port.out.AdapterUnavailableException;
import com.bittle.orchestrator.application.port.out.RobotAdapterPort;
import com.bittle.orchestrator.domain.fleet.Fleet;
import com.bittle.orchestrator.domain.fleet.Robot;
import com.bittle.orchestrator.domain.robot.BinaryContent;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class SensorStateServiceTest {

    private static final Instant T0 = Instant.parse("2026-10-11T21:30:00Z");
    private static final Robot LAIKA = new Robot("bittle-1", "Laika", "bittle_x_v2", "http://laika");
    private static final byte[] JPEG = {(byte) 0xFF, (byte) 0xD8, 1, 2};

    private final RobotAdapterPort adapter = mock(RobotAdapterPort.class);
    private final MutableClock clock = new MutableClock(T0);
    private SensorStateService service;

    @BeforeEach
    void setUp() {
        service = new SensorStateService(new Fleet(List.of(LAIKA)), adapter, clock,
                SensorStateService.DEFAULT_TTL);
    }

    @Test
    void givenAllSourcesAnswer_whenCaptured_thenReadingsAreMappedAndUnitsConverted() {
        allSources(0.5, -0.25, 90.0, 16384);

        var snapshot = service.captureSnapshot("bittle-1");

        assertThat(snapshot.capturedAt()).isEqualTo(T0);
        assertThat(snapshot.odometryPosition().xCm()).isEqualTo(50.0);
        assertThat(snapshot.odometryPosition().yCm()).isEqualTo(-25.0);
        assertThat(snapshot.odometryPosition().headingDeg()).isEqualTo(90.0);
        assertThat(snapshot.audioAmplitudePeak()).isEqualTo(0.5);
        assertThat(snapshot.cameraFrame()).containsExactly(JPEG);
        assertThat(snapshot.headImu()).isNull();
    }

    @Test
    void givenSourcesFail_whenCaptured_thenMissingReadingsAreNullAndNothingThrows() {
        when(adapter.get(LAIKA, "/senses"))
                .thenThrow(new AdapterUnavailableException("http://laika", null));
        when(adapter.get(LAIKA, "/ears")).thenReturn(Map.of("enabled", true));
        when(adapter.getBinary(LAIKA, "/eyes/snap"))
                .thenThrow(new AdapterErrorException(404, "{\"error\":\"no_frame\"}"));

        var snapshot = service.captureSnapshot("bittle-1");

        assertThat(snapshot.odometryPosition()).isNull();
        assertThat(snapshot.audioAmplitudePeak()).isNull();
        assertThat(snapshot.hasCameraFrame()).isFalse();
        assertThat(service.getSnapshotAt("bittle-1", T0)).contains(snapshot);
    }

    @Test
    void givenNonImageBody_whenCaptured_thenNoCameraFrame() {
        allSources(0, 0, 0, 0);
        when(adapter.getBinary(LAIKA, "/eyes/snap"))
                .thenReturn(new BinaryContent("{}".getBytes(), "application/json"));

        assertThat(service.captureSnapshot("bittle-1").hasCameraFrame()).isFalse();
    }

    @Test
    void givenPeakAboveFullScale_whenCaptured_thenAmplitudeIsClamped() {
        allSources(0, 0, 0, 99999);

        assertThat(service.captureSnapshot("bittle-1").audioAmplitudePeak()).isEqualTo(1.0);
    }

    @Test
    void givenUnknownRobot_whenCaptured_thenEmptySnapshotAndNoAdapterCall() {
        var snapshot = service.captureSnapshot("ghost");

        assertThat(snapshot.odometryPosition()).isNull();
        assertThat(service.cachedCount()).isZero();
        verifyNoInteractions(adapter);
    }

    @Test
    void givenSeveralSnapshots_whenAskedForAMoment_thenTheNewestAtOrBeforeItIsReturned() {
        allSources(0.0, 0, 0, 0);
        var first = service.captureSnapshot("bittle-1");
        clock.advance(Duration.ofSeconds(2));
        allSources(0.1, 0, 0, 0);
        var second = service.captureSnapshot("bittle-1");

        assertThat(service.getSnapshotAt("bittle-1", T0.minusSeconds(1))).isEmpty();
        assertThat(service.getSnapshotAt("bittle-1", T0)).contains(first);
        assertThat(service.getSnapshotAt("bittle-1", T0.plusSeconds(1))).contains(first);
        assertThat(service.getSnapshotAt("bittle-1", T0.plusSeconds(5))).contains(second);
        assertThat(service.latestSnapshot("bittle-1")).contains(second);
        assertThat(service.getSnapshotAt("other", T0)).isEmpty();
    }

    @Test
    void givenSnapshots_whenInvalidatedBefore_thenOnlyOlderOnesAreRemoved() {
        allSources(0, 0, 0, 0);
        service.captureSnapshot("bittle-1");
        clock.advance(Duration.ofSeconds(10));
        var kept = service.captureSnapshot("bittle-1");

        int removed = service.invalidateSnapshotsBefore(T0.plusSeconds(10));

        assertThat(removed).isEqualTo(1);
        assertThat(service.cachedCount()).isEqualTo(1);
        assertThat(service.getSnapshotAt("bittle-1", T0.plusSeconds(10))).contains(kept);
    }

    @Test
    void givenTtlPassed_whenRead_thenExpiredSnapshotsAreGone() {
        allSources(0, 0, 0, 0);
        service.captureSnapshot("bittle-1");

        clock.advance(Duration.ofMinutes(9));
        assertThat(service.getSnapshotAt("bittle-1", clock.instant())).isPresent();

        clock.advance(Duration.ofMinutes(2));
        assertThat(service.getSnapshotAt("bittle-1", clock.instant())).isEmpty();
        assertThat(service.cachedCount()).isZero();
    }

    @Test
    void givenManyCaptures_whenCached_thenThePerRobotCapIsKept() {
        allSources(0, 0, 0, 0);
        for (int i = 0; i < SensorStateService.MAX_SNAPSHOTS_PER_ROBOT + 10; i++) {
            service.captureSnapshot("bittle-1");
            clock.advance(Duration.ofMillis(100));
        }

        assertThat(service.cachedCount()).isEqualTo(SensorStateService.MAX_SNAPSHOTS_PER_ROBOT);
        assertThat(service.getSnapshotAt("bittle-1", T0)).isEmpty();
    }

    @Test
    void givenNonPositiveTtl_whenCreated_thenRejected() {
        assertThatThrownBy(() -> new SensorStateService(new Fleet(List.of(LAIKA)), adapter, clock,
                Duration.ZERO)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void givenPoseWithoutCoordinates_whenMapped_thenNoOdometry() {
        assertThat(SensorStateService.odometry(Map.of("pose", Map.of("heading", 10)))).isNull();
        assertThat(SensorStateService.odometry(Map.of("pose", "n/a"))).isNull();
        assertThat(SensorStateService.audioPeak(Map.of("level", Map.of("rms", 3)))).isNull();
    }

    private void allSources(double xM, double yM, double heading, int peak) {
        when(adapter.get(eq(LAIKA), eq("/senses"))).thenReturn(Map.of("pose",
                Map.of("x", xM, "y", yM, "heading", heading)));
        when(adapter.get(eq(LAIKA), eq("/ears"))).thenReturn(Map.of("level",
                Map.of("rms", 10, "peak", peak)));
        when(adapter.getBinary(any(), eq("/eyes/snap")))
                .thenReturn(new BinaryContent(JPEG, "image/jpeg"));
    }

    private static final class MutableClock extends Clock {
        private Instant now;

        MutableClock(Instant start) {
            this.now = start;
        }

        void advance(Duration step) {
            now = now.plus(step);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return now;
        }
    }
}

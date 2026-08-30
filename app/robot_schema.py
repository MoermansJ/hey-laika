"""Capability schema for the robot this adapter serves.

The /schema endpoint reports what is controllable so the orchestrator GUI can
render generically (sliders, action buttons, sensor tiles) without hardcoding
a servo count. For the MVP the Bittle X V2 schema is defined statically here.

Servo min/max are CONSERVATIVE ESTIMATES from quadruped conventions — the
protocol allows ±125 but mechanical limits are narrower and unmeasured. Run
the per-joint limit test (GUI plan Milestone 4) before widening them.
"""
from dataclasses import asdict, dataclass


@dataclass
class ServoCapability:
    index: int
    name: str
    displayName: str
    group: str
    min: int
    max: int
    unit: str
    description: str


@dataclass
class ActionCapability:
    id: str
    name: str
    displayName: str
    category: str
    durationMs: int
    description: str
    verified: bool  # True = exercised against firmware B10_251121 live


@dataclass
class SensorCapability:
    id: str
    name: str
    displayName: str
    type: str
    unit: str
    min: float
    max: float
    description: str
    available: bool


BITTLE_SERVOS = [
    ServoCapability(0, "head_pan", "Head Pan", "head", -90, 90, "°",
                    "Neck yaw (left/right)"),
    ServoCapability(8, "front_left_hip", "Front Left Hip", "leg_fl", -60, 60,
                    "°", "Hip flexion (forward/back)"),
    ServoCapability(9, "front_right_hip", "Front Right Hip", "leg_fr", -60, 60,
                    "°", "Hip flexion (forward/back)"),
    ServoCapability(10, "back_right_hip", "Back Right Hip", "leg_br", -60, 60,
                    "°", "Hip flexion (forward/back)"),
    ServoCapability(11, "back_left_hip", "Back Left Hip", "leg_bl", -60, 60,
                    "°", "Hip flexion (forward/back)"),
    ServoCapability(12, "front_left_knee", "Front Left Knee", "leg_fl", -90, 30,
                    "°", "Knee bend (extend/contract)"),
    ServoCapability(13, "front_right_knee", "Front Right Knee", "leg_fr", -90, 30,
                    "°", "Knee bend (extend/contract)"),
    ServoCapability(14, "back_right_knee", "Back Right Knee", "leg_br", -90, 30,
                    "°", "Knee bend (extend/contract)"),
    ServoCapability(15, "back_left_knee", "Back Left Knee", "leg_bl", -90, 30,
                    "°", "Knee bend (extend/contract)"),
]

# Skill tokens from the choreography library. Durations are estimates from the
# desktop app; only 'verified' ones were exercised live on B10_251121.
BITTLE_ACTIONS = [
    ActionCapability("kbalance", "balance", "Balance", "posture", 500,
                     "Standing balance posture", True),
    ActionCapability("ksit", "sit", "Sit", "posture", 2000,
                     "Sit down posture", False),
    ActionCapability("krest", "rest", "Rest", "posture", 2000,
                     "Rest / lie down", True),
    ActionCapability("kwkF", "walk_forward", "Walk Forward", "gait", 3000,
                     "Forward walking gait", False),
    ActionCapability("kvtR", "turn_right", "Turn Right", "gait", 2500,
                     "Turn in place, right", False),
    ActionCapability("kvtL", "turn_left", "Turn Left", "gait", 2500,
                     "Turn in place, left", False),
    ActionCapability("khi", "wave", "Say Hi", "trick", 2000,
                     "Wave a front leg", False),
    ActionCapability("kstr", "stretch", "Stretch", "trick", 2500,
                     "Morning stretch", False),
    ActionCapability("kjmp", "jump", "Jump", "trick", 1500,
                     "Hop in place", False),
    ActionCapability("ksnf", "sniff", "Sniff", "trick", 2000,
                     "Lower head and sniff", False),
    ActionCapability("kpd", "play_dead", "Play Dead", "trick", 3000,
                     "Flop over dramatically", False),
]

BITTLE_SENSORS = [
    SensorCapability("battery", "battery_percent", "Battery", "percent", "%",
                     0, 100, "Battery charge level", False),
    SensorCapability("imu_pitch", "imu_pitch", "IMU Pitch", "angle", "°",
                     -180, 180, "Body pitch (forward/back tilt)", False),
    SensorCapability("imu_roll", "imu_roll", "IMU Roll", "angle", "°",
                     -180, 180, "Body roll (side tilt)", False),
    SensorCapability("wifi_signal", "wifi_rssi", "WiFi Signal", "rssi", "dBm",
                     -90, -30, "WiFi RSSI", False),
    SensorCapability("back_touch", "back_touch", "Back Touch", "integer", "raw",
                     0, 2400, "Back touch sensor (analog pin 38, 6 buckets)",
                     False),
]

SERVO_LIMITS = {s.index: (s.min, s.max) for s in BITTLE_SERVOS}
SERVO_INDICES = tuple(SERVO_LIMITS)


def build_schema() -> dict:
    return {
        "servos": [asdict(s) for s in BITTLE_SERVOS],
        "actions": [asdict(a) for a in BITTLE_ACTIONS],
        "sensors": [asdict(s) for s in BITTLE_SENSORS],
    }

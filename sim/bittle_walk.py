"""Watch Bittle walk using the rule-based gait in gait.py — no RL, just a
hand-written trajectory for each leg. Edit the numbers in gait.PARAMS (or
the LEGS phase offsets / swing-stance formulas) and rerun to see the effect.
"""
import time
import numpy as np
import pybullet as p
import pybullet_data

import gait

JOINT_ORDER = [2, 3, 4, 5, 8, 9, 10, 11]  # left-back-sh/kn, left-front-sh/kn, right-back-sh/kn, right-front-sh/kn
DT = 1 / 240
SETTLE_S = 1.0

# --- Visuals (edit freely — purely cosmetic, doesn't affect physics) ---
BODY_COLOR = [0.95, 0.55, 0.10, 1.0]   # orange chassis
LEG_COLOR = [0.15, 0.65, 0.85, 1.0]    # cyan legs, for contrast against the orange body
GROUND_COLOR = [0.35, 0.55, 0.35, 1.0]  # muted green instead of the default blue/white checker
CAMERA_ZOOM_MARGIN = 2.4  # multiplier on the robot's own size to pick a camera distance that fits it in frame

p.connect(p.GUI, options="--width=1280 --height=800")
p.configureDebugVisualizer(p.COV_ENABLE_GUI, 1)
p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1)
p.setGravity(0, 0, -9.81)
p.setAdditionalSearchPath(pybullet_data.getDataPath())

plane_id = p.loadURDF("plane.urdf")
p.changeDynamics(plane_id, -1, lateralFriction=1.4)
p.changeVisualShape(plane_id, -1, rgbaColor=GROUND_COLOR)

start_pos = [0, 0, 0.6]
start_orn = p.getQuaternionFromEuler([0, 0, -1.5708])
bittle_id = p.loadURDF("bittle-simulation/models/bittle_modified.urdf", start_pos, start_orn)

# Recolor every link: fixed-mount links (battery/cover/mainboard/imu) + the base match the body,
# revolute leg links (shoulder/knee) get the contrasting leg color.
p.changeVisualShape(bittle_id, -1, rgbaColor=BODY_COLOR)
for j in range(p.getNumJoints(bittle_id)):
    joint_type = p.getJointInfo(bittle_id, j)[2]
    color = LEG_COLOR if joint_type == p.JOINT_REVOLUTE else BODY_COLOR
    p.changeVisualShape(bittle_id, j, rgbaColor=color)

print("Gait parameters (edit gait.py and rerun to change):")
for k, v in gait.PARAMS.items():
    print(f"  {k}: {v}")

# Settle onto the ground under gravity before the gait starts
for _ in range(int(SETTLE_S / DT)):
    p.stepSimulation()

# Size the camera to the robot's actual footprint so it's fully in frame, zoomed out with margin
aabb_min, aabb_max = p.getAABB(bittle_id)
for j in range(p.getNumJoints(bittle_id)):
    link_min, link_max = p.getAABB(bittle_id, j)
    aabb_min = [min(a, b) for a, b in zip(aabb_min, link_min)]
    aabb_max = [max(a, b) for a, b in zip(aabb_max, link_max)]
robot_extent = max(hi - lo for lo, hi in zip(aabb_min, aabb_max))
camera_dist = robot_extent * CAMERA_ZOOM_MARGIN
camera_yaw, camera_pitch = -35, -25
print(f"Robot extent ~{robot_extent:.2f}m -> camera distance {camera_dist:.2f}m")

t = 0.0
last_print = 0.0
while True:
    targets = gait.leg_targets(t, gait.PARAMS)
    p.setJointMotorControlArray(bittle_id, JOINT_ORDER, p.POSITION_CONTROL, targets)
    p.stepSimulation()

    base_pos, _ = p.getBasePositionAndOrientation(bittle_id)
    p.resetDebugVisualizerCamera(cameraDistance=camera_dist, cameraYaw=camera_yaw, cameraPitch=camera_pitch, cameraTargetPosition=base_pos)

    if t - last_print >= 1.0:
        print(f"t={t:5.1f}s  base=({base_pos[0]:+.2f}, {base_pos[1]:+.2f}, {base_pos[2]:.2f})")
        last_print = t

    t += DT
    time.sleep(DT)

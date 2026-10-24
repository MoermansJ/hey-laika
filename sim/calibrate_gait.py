"""Headless (DIRECT, no window) quick check: does the trot in gait.py
actually move the robot forward without falling over? Prints displacement
so the direction/amplitude can be sanity-checked before watching it live.
"""
import pybullet as p
import pybullet_data
import numpy as np
import time
import gait

JOINT_ORDER = [2, 3, 4, 5, 8, 9, 10, 11]  # same mapping used by bittle_manual.py / verify_render.py


def run_trial(params, duration_s=10.0, settle_s=1.0, dt=1 / 240):
    p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.81)
    plane_id = p.loadURDF("plane.urdf")
    p.changeDynamics(plane_id, -1, lateralFriction=1.4)

    start_pos = [0, 0, 0.6]
    start_orn = p.getQuaternionFromEuler([0, 0, -1.5708])
    bittle_id = p.loadURDF("bittle-simulation/models/bittle_modified.urdf", start_pos, start_orn)

    # Let the robot settle onto its feet under gravity before gait motion starts
    for _ in range(int(settle_s / dt)):
        p.stepSimulation()

    steps = int(duration_s / dt)
    t = 0.0
    for _ in range(steps):
        targets = gait.leg_targets(t, params)
        p.setJointMotorControlArray(bittle_id, JOINT_ORDER, p.POSITION_CONTROL, targets)
        p.stepSimulation()
        t += dt

    pos, orn = p.getBasePositionAndOrientation(bittle_id)
    euler = p.getEulerFromQuaternion(orn)
    fallen = abs(euler[0]) > 1.0 or abs(euler[1]) > 1.0 or pos[2] < 0.15
    p.disconnect()
    return pos, fallen


if __name__ == "__main__":
    for direction in (1, -1):
        params = dict(gait.PARAMS)
        params["direction"] = direction
        pos, fallen = run_trial(params)
        print(f"direction={direction:+d}  end_pos=({pos[0]:+.3f}, {pos[1]:+.3f}, {pos[2]:.3f})  fallen={fallen}")

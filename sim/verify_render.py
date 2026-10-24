"""One-off MVP check: load the Bittle URDF into a PyBullet GUI session,
let physics settle, and save a camera screenshot so rendering can be
verified without needing eyes on the live window.
"""
import pybullet as p
import pybullet_data
from PIL import Image
import numpy as np
import os

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
URDF_PATH = os.path.join(SIM_DIR, "bittle-simulation", "models", "bittle_modified.urdf")
OUT_PATH = os.path.join(SIM_DIR, "render_check.png")

p.connect(p.GUI)
p.configureDebugVisualizer(p.COV_ENABLE_GUI, 1)
p.resetDebugVisualizerCamera(cameraDistance=0.6, cameraYaw=-10, cameraPitch=-30, cameraTargetPosition=[0.4, 0, 0])
p.setGravity(0, 0, -9.81)

p.setAdditionalSearchPath(pybullet_data.getDataPath())
plane_id = p.loadURDF("plane.urdf")
p.changeDynamics(plane_id, -1, lateralFriction=1.4)

start_pos = [0, 0, 0.6]
start_orn = p.getQuaternionFromEuler([0, 0, -1.5708])
bittle_id = p.loadURDF(URDF_PATH, start_pos, start_orn)

print(f"Loaded bittle with {p.getNumJoints(bittle_id)} joints:")
for j in range(p.getNumJoints(bittle_id)):
    info = p.getJointInfo(bittle_id, j)
    print(f"  joint {j}: {info[1].decode('utf-8')} type={info[2]}")

for _ in range(300):
    p.stepSimulation()

aabb_min, aabb_max = p.getAABB(bittle_id)
for j in range(p.getNumJoints(bittle_id)):
    link_min, link_max = p.getAABB(bittle_id, j)
    aabb_min = [min(a, b) for a, b in zip(aabb_min, link_min)]
    aabb_max = [max(a, b) for a, b in zip(aabb_max, link_max)]
center = [(lo + hi) / 2 for lo, hi in zip(aabb_min, aabb_max)]
extent = max(hi - lo for lo, hi in zip(aabb_min, aabb_max))
print(f"AABB min={aabb_min} max={aabb_max} center={center} extent={extent}")

width, height = 960, 720
view_matrix = p.computeViewMatrixFromYawPitchRoll(
    cameraTargetPosition=center,
    distance=extent * 2.2,
    yaw=45,
    pitch=-30,
    roll=0,
    upAxisIndex=2,
)
proj_matrix = p.computeProjectionMatrixFOV(fov=60, aspect=width / height, nearVal=0.01, farVal=5)
img = p.getCameraImage(
    width, height, viewMatrix=view_matrix, projectionMatrix=proj_matrix,
    renderer=p.ER_BULLET_HARDWARE_OPENGL,
    lightDirection=[1, 1, 1], shadow=1,
)
rgb = np.reshape(img[2], (height, width, 4))[:, :, :3]
Image.fromarray(rgb.astype(np.uint8)).save(OUT_PATH)
print(f"Saved screenshot to {OUT_PATH}")

final_pos, final_orn = p.getBasePositionAndOrientation(bittle_id)
print(f"Bittle base position after settling: {final_pos}")

p.disconnect()

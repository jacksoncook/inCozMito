# InCozMito - Group #1 - Jackson Cook, Harsh Patel

## If you run into an "[NSApplication _setup] unrecognized selector" problem on macOS,
## try uncommenting the following snippet

# try:
#     import matplotlib
#     matplotlib.use('TkAgg')
# except ImportError:
#     pass

from skimage import color
import cozmo
import numpy as np
from numpy.linalg import inv
import threading
import time
import sys
import asyncio
from PIL import Image
import math

from markers import detect, annotator

from grid import CozGrid
from gui import GUIWindow
from particle import Particle, Robot
from setting import *
from particle_filter import *
from utils import *

#particle filter functionality
class ParticleFilter:

    def __init__(self, grid):
        self.particles = Particle.create_random(PARTICLE_COUNT, grid)
        self.grid = grid

    def update(self, odom, r_marker_list):

        # ---------- Motion model update ----------
        self.particles = motion_update(self.particles, odom)

        # ---------- Sensor (markers) model update ----------
        self.particles = measurement_update(self.particles, r_marker_list, self.grid)

        # ---------- Show current state ----------
        # Try to find current best estimate for display
        m_x, m_y, m_h, m_confident = compute_mean_pose(self.particles)
        return (m_x, m_y, m_h, m_confident)

# tmp cache
last_pose = cozmo.util.Pose(0,0,0,angle_z=cozmo.util.Angle(degrees=0))
flag_odom_init = False

# goal location for the robot to drive to, (x, y, theta)
goal = (6, 12, 0)

# map
Map_filename = "map_arena.json"
grid = CozGrid(Map_filename)
gui = GUIWindow(grid, show_camera=True)
pf = ParticleFilter(grid)

robot_PickedUp = False
robot_ReachedGoal = False

def compute_odometry(curr_pose, cvt_inch=True):
    '''
    Compute the odometry given the current pose of the robot (use robot.pose)

    Input:
        - curr_pose: a cozmo.robot.Pose representing the robot's current location
        - cvt_inch: converts the odometry into grid units
    Returns:
        - 3-tuple (dx, dy, dh) representing the odometry
    '''

    global last_pose, flag_odom_init
    last_x, last_y, last_h = last_pose.position.x, last_pose.position.y, \
        last_pose.rotation.angle_z.degrees
    curr_x, curr_y, curr_h = curr_pose.position.x, curr_pose.position.y, \
        curr_pose.rotation.angle_z.degrees

    dx, dy = rotate_point(curr_x-last_x, curr_y-last_y, -last_h)
    if cvt_inch:
        dx, dy = dx / grid.scale, dy / grid.scale

    return (dx, dy, diff_heading_deg(curr_h, last_h))


async def marker_processing(robot, camera_settings, show_diagnostic_image=False):
    '''
    Obtain the visible markers from the current frame from Cozmo's camera.
    Since this is an async function, it must be called using await, for example:

        markers, camera_image = await marker_processing(robot, camera_settings, show_diagnostic_image=False)

    Input:
        - robot: cozmo.robot.Robot object
        - camera_settings: 3x3 matrix representing the camera calibration settings
        - show_diagnostic_image: if True, shows what the marker detector sees after processing
    Returns:
        - a list of detected markers, each being a 3-tuple (rx, ry, rh)
          (as expected by the particle filter's measurement update)
        - a PIL Image of what Cozmo's camera sees with marker annotations
    '''

    global grid

    # Wait for the latest image from Cozmo
    image_event = await robot.world.wait_for(cozmo.camera.EvtNewRawCameraImage, timeout=30)

    # Convert the image to grayscale
    image = np.array(image_event.image)
    image = color.rgb2gray(image)

    # Detect the markers
    markers, diag = detect.detect_markers(image, camera_settings, include_diagnostics=True)

    # Measured marker list for the particle filter, scaled by the grid scale
    marker_list = [marker['xyh'] for marker in markers]
    marker_list = [(x/grid.scale, y/grid.scale, h) for x,y,h in marker_list]

    # Annotate the camera image with the markers
    if not show_diagnostic_image:
        annotated_image = image_event.image.resize((image.shape[1] * 2, image.shape[0] * 2))
        annotator.annotate_markers(annotated_image, markers, scale=2)
    else:
        diag_image = color.gray2rgb(diag['filtered_image'])
        diag_image = Image.fromarray(np.uint8(diag_image * 255)).resize((image.shape[1] * 2, image.shape[0] * 2))
        annotator.annotate_markers(diag_image, markers, scale=2)
        annotated_image = diag_image

    return marker_list, annotated_image

async def run(robot: cozmo.robot.Robot):

    global flag_odom_init, last_pose
    global grid, gui, pf

    # start streaming
    robot.camera.image_stream_enabled = True
    robot.camera.color_image_enabled = False
    robot.camera.enable_auto_exposure()
    await robot.set_head_angle(cozmo.util.degrees(0)).wait_for_completed()

    # Obtain the camera intrinsics matrix
    fx, fy = robot.camera.config.focal_length.x_y
    cx, cy = robot.camera.config.center.x_y
    camera_settings = np.array([
        [fx,  0, cx],
        [ 0, fy, cy],
        [ 0,  0,  1]
    ], dtype=np.float)

    ###################

    # YOUR CODE HERE
    # Edited detect.py to have opening = 5 instead of opening = 1
    ###################
    global robot_PickedUp, robot_ReachedGoal

    while True:
        if not compute_mean_pose(pf.particles)[3]:
            if robot.is_picked_up:
                print("Kidnapped!")
                await robot.play_anim_trigger(cozmo.anim.Triggers.KnockOverFailure, in_parallel=True).wait_for_completed()
                pf = ParticleFilter(grid)
                time.sleep(1)
            else:
                # Reset Head Angle
                await robot.set_head_angle(cozmo.util.degrees(10)).wait_for_completed()
                # Move Robot around
                await robot.drive_wheels(5, 25)
                # Compute Odometry
                currPose = robot.pose
                robot_odometry = compute_odometry(currPose)
                # Obtain Marker Information
                observed_markersList, camera_image = await marker_processing(robot, camera_settings, show_diagnostic_image=False)
                # Pass Marker Information into Pf
                mean_estimate = pf.update(robot_odometry, observed_markersList)
                # Update the GUI
                gui.show_particles(pf.particles)
                gui.show_mean(mean_estimate[0], mean_estimate[1], mean_estimate[2], mean_estimate[3])
                gui.show_camera_image(camera_image)
                gui.updated.set()
                # Update last_pose
                last_pose = currPose
        else:
            # Stop all robot movement
            robot.stop_all_motors()
            if not robot_ReachedGoal:
                # Calculate distance to Goal and angle to Goal
                mean_x, mean_y, mean_h, mean_c = compute_mean_pose(pf.particles)
                goal_x, goal_y, goal_h = (goal[0], goal[1], goal[2])

                diff_x = goal_x - mean_x
                diff_y = goal_y - mean_y
                diff_h = math.degrees(math.atan2(diff_y, diff_x))

                final_distance = math.sqrt((diff_y ** 2) + (diff_x ** 2)) * 25.4
                turn_angle = diff_heading_deg(diff_h, mean_h)

                transformation_matrix = [[math.cos(mean_h), -math.sin(mean_h), mean_x],
                        [math.sin(mean_h), math.cos(mean_h), mean_y],
                        [0, 0, 1]]
                transformation_matrix = np.linalg.inv(transformation_matrix)
                local_pos = [goal_x, goal_y, 1]
                product = np.matmul(transformation_matrix, local_pos)
                localX, localY = product[0], product[1]
                print("Mean_x: " + str(mean_x) + " Mean_y: " + str(mean_y) + " Mean_h: " + str(mean_h))
                print("LocalX: " + str(localX) + " LocalY: " + str(localY))
                await robot.go_to_pose(cozmo.util.Pose(product[0] * 25.4, -product[1] * 25.4, 0, angle_z=cozmo.util.degrees(0)), relative_to_robot=True).wait_for_completed()

                # Turn toward Goal
                # if not robot.is_picked_up:
                #     await robot.turn_in_place(cozmo.util.degrees(turn_angle)).wait_for_completed()
                # else:
                #     print("Kidnapped!")
                #     await robot.play_anim_trigger(cozmo.anim.Triggers.KnockOverFailure, in_parallel=True).wait_for_completed()
                #     pf = ParticleFilter(grid)
                #     time.sleep(1)
                #     continue

                # distance_driven = 0
                driving_Kidnapped = False
                # # Drive to Goal
                # while distance_driven < final_distance:
                #     if robot.is_picked_up:
                #         print("Kidnapped!")
                #         await robot.play_anim_trigger(cozmo.anim.Triggers.BlockReact, in_parallel=True).wait_for_completed()
                #         pf = ParticleFilter(grid)
                #         time.sleep(1)
                #         driving_Kidnapped = True
                #         break
                #     currentPose = robot.pose
                #     curr_X = currentPose.position.x
                #     curr_Y = currentPose.position.y
                #     curr_H = currentPose.rotation.angle_z.radians

                #     transformation_matrix = [[math.cos(mean_h), -math.sin(mean_h), mean_x],
                #             [math.sin(mean_h), math.cos(mean_h), mean_y],
                #             [0, 0, 1]]
                #     local_pos = [curr_X, curr_Y, 1]
                #     product = np.matmul(transformation_matrix, local_pos)
                #     globalX, globalY = product[0], product[1]
                #     print("Goal x: " + str(goal_x) + " Robot x: " + str(globalX))
                #     print("Goal y: " + str(goal_y) + " Robot y: " + str(globalY))
                #     from cozmo.util import degrees, Pose
                #     await robot.go_to_pose(Pose(goal_x * 25.4 - globalX, goal_y * 25.4 - globalY, 0, angle_z=degrees(0)), relative_to_robot=True).wait_for_completed()
                #     # await robot.drive_straight(cozmo.util.distance_mm(min(40, final_distance - distance_driven)), cozmo.util.speed_mmps(40)).wait_for_completed()

                #     distance_driven += final_distance

                if driving_Kidnapped:
                    continue
                # Turn to Goal Heading and Set robot.GoalReached
                if robot.is_picked_up:
                    print("Kidnapped!")
                    await robot.play_anim_trigger(cozmo.anim.Triggers.KnockOverFailure, in_parallel=True).wait_for_completed()
                    pf = ParticleFilter(grid)
                    time.sleep(1)
                    continue
                else:
                    # await robot.turn_in_place(cozmo.util.degrees(goal_h - diff_h)).wait_for_completed()
                    robot_ReachedGoal = True
            else:
                # Reached Goal - Chill Here
                await robot.play_anim_trigger(cozmo.anim.Triggers.BlockReact).wait_for_completed()
                if robot.is_picked_up:
                    print("Kidnapped!")
                    robot_ReachedGoal = False
                    await robot.play_anim_trigger(cozmo.anim.Triggers.KnockOverFailure, in_parallel=True).wait_for_completed()
                    pf = ParticleFilter(grid)
                    time.sleep(1)
                    continue

class CozmoThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self, daemon=False)

    def run(self):
        cozmo.robot.Robot.drive_off_charger_on_connect = False  # Cozmo can stay on his charger
        cozmo.run_program(run, use_viewer=False)


if __name__ == '__main__':

    # cozmo thread
    cozmo_thread = CozmoThread()
    cozmo_thread.start()

    # init
    gui.show_particles(pf.particles)
    gui.show_mean(0, 0, 0)
    gui.start()


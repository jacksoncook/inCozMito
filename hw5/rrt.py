import cozmo
import math
import sys
import time
import numpy as np

from cmap import *
from gui import *
from utils import *

MAX_NODES = 20000


def step_from_to(node0, node1, limit=75):
    import math
    ########################################################################
    # TODO: please enter your code below.
    # 1. If distance between two nodes is less than limit, return node1
    # 2. Otherwise, return a node in the direction from node0 to node1 whose
    #    distance to node0 is limit. Recall that each iteration we can move
    #    limit units at most
    # 3. Hint: please consider using np.arctan2 function to get vector angle
    # 4. Note: remember always return a Node object
    if (get_dist(node0, node1) < limit):
        return node1
    else:
        angle_theta = np.arctan2(node1.y - node0.y, node1.x - node0.x)
        return Node((node0.x + limit * math.cos(angle_theta), node0.y + limit * math.sin(angle_theta)))
    ############################################################################

def node_generator(cmap):
    import random

    rand_node = Node((random.random() * cmap.width, random.random() * cmap.height))
    while cmap.is_inside_obstacles(rand_node) or not cmap.is_inbound(rand_node):
        rand_node = Node((random.random() * cmap.width, random.random() * cmap.height))
    if random.random() < 0.95:
        return rand_node
    else:
        return Node(cmap.get_goals()[random.randint(0, len(cmap.get_goals()) - 1)])
    ############################################################################
    # TODO: please enter your code below.
    # 1. Use CozMap width and height to get a uniformly distributed random node
    # 2. Use CozMap.is_inbound and CozMap.is_inside_obstacles to determine the
    #    legitimacy of the random node.
    # 3. Note: remember always return a Node object
    ############################################################################

def RRT(cmap, start):
    cmap.add_node(start)
    map_width, map_height = cmap.get_size()
    while (cmap.get_num_nodes() < MAX_NODES):
        ########################################################################
        # TODO: please enter your code below.
        # 1. Use CozMap.get_random_valid_node() to get a random node. This
        #    function will internally call the node_generator above
        # 2. Get the nearest node to the random node from RRT
        # 3. Limit the distance RRT can move
        # 4. Add one path from nearest node to random node
        #
        rand_node = cmap.get_random_valid_node()
        all_nodes = cmap.get_nodes()
        nearest_node = all_nodes[0]
        for node in all_nodes:
            if get_dist(rand_node, node) < get_dist(rand_node, nearest_node):
                nearest_node = node
        rand_node = step_from_to(nearest_node, rand_node)

        ########################################################################
        time.sleep(0.01)
        if not cmap.is_collision_with_obstacles((rand_node, nearest_node)):
            cmap.add_path(nearest_node, rand_node)
        if cmap.is_solved():
            print("Solved")
            break

    path = cmap.get_path()
    smoothed_path = cmap.get_smooth_path()

    if cmap.is_solution_valid():
        print("A valid solution has been found :-) ")
        print("Nodes created: ", cmap.get_num_nodes())
        print("Path length: ", len(path))
        print("Smoothed path length: ", len(smoothed_path))
    else:
        print("Please try again :-(")

def diff_heading_deg(heading1, heading2):
    dh = heading1 - heading2
    while dh > 180:
        dh -= 360
    while dh <= -180:
        dh += 360
    return dh

async def CozmoPlanning(robot: cozmo.robot.Robot):
    # Allows access to map and stopevent, which can be used to see if the GUI
    # has been closed by checking stopevent.is_set()
    global cmap, stopevent

    markers = dict()
    await robot.set_head_angle(cozmo.util.degrees(0)).wait_for_completed()
    update, center = await detect_cube_and_update_cmap(robot, markers, cmap.get_start())
    if center is None:
        cmap.add_goal(Node((325,225)))
        RRT(cmap, cmap.get_start())
    else:
        RRT(cmap, cmap.get_start())
    path = cmap.get_smooth_path()

    count = 0
    currentAngle = 0
    while count != (len(path) - 1):
        currNode = path[count]
        nextNode = path[count + 1]
        diff_x = nextNode.x - currNode.x
        diff_y = nextNode.y - currNode.y

        diff_h = math.degrees(math.atan2(diff_y, diff_x))
        final_distance = math.sqrt((diff_y ** 2) + (diff_x ** 2))
        turn_angle = diff_heading_deg(diff_h, currentAngle)

        await robot.turn_in_place(cozmo.util.degrees(turn_angle)).wait_for_completed()
        await robot.drive_straight(cozmo.util.distance_mm(final_distance), cozmo.util.speed_mmps(40)).wait_for_completed()

        currentAngle = turn_angle
        count = count + 1
    print("Arrived!")

# class StateMachine:

#     def __init__(self):
#         self.state = Idle()

#     def start(self):
#         while True:
#             print("While loop")
#             self.state.run(self)

# class State(object):

#     def run(self, stateMachine):
#         assert 0

# class Idle(State):
#     def run(self, stateMachine):
#         global ROBOT_INSTANCE

#         robot = ROBOT_INSTANCE
#         print("Idle")
#         robot.say_text("Hello").wait_for_completed()
#         stateMachine.state = Idle()
#         # if predicted_label == "drone":
#         #     print("drone")
#         #     stateMachine.state = Drone()
#         # elif predicted_label == "order":
#         #     print("order")
#         #     stateMachine.state = Order()
#         # elif predicted_label == "inspection":
#         #     print("inspection")
#         #     stateMachine.state = Inspection()
#         # else:
#         #     print("idle")
#         #     stateMachine.state = Idle()

class Order(State):
    def run(self, stateMachine):
        global ROBOT_INSTANCE
        robot = ROBOT_INSTANCE

        stateMachine.state = Idle()

class Inspection(State):
    def run(self, stateMachine):
        global ROBOT_INSTANCE
        robot = ROBOT_INSTANCE

        robot.say_text("Running Inspection").wait_for_completed()
        stateMachine.state = Idle()

class Drone(State):
    def run(self, stateMachine):
        global ROBOT_INSTANCE
        robot = ROBOT_INSTANCE

        robot.say_text("Running Drone").wait_for_completed()
        stateMachine.state = Idle()


def get_global_node(local_angle, local_origin, node):
    """Helper function: Transform the node's position (x,y) from local coordinate frame specified by local_origin and local_angle to global coordinate frame.
                        This function is used in detect_cube_and_update_cmap()
        Arguments:
        local_angle, local_origin -- specify local coordinate frame's origin in global coordinate frame
        local_angle -- a single angle value
        local_origin -- a Node object

        Outputs:
        new_node -- a Node object that decribes the node's position in global coordinate frame
    """
    ########################################################################
    # TODO: please enter your code below.
    new_node = None
    transformation_matrix = [[math.cos(local_angle), -math.sin(local_angle), local_origin.x],
                            [math.sin(local_angle), math.cos(local_angle), local_origin.y],
                            [0, 0, 1]]
    local_pos = [node.x, node.y, 1]
    product = np.matmul(transformation_matrix, local_pos)
    new_node = Node((product[0], product[1]))
    return new_node

async def detect_cube_and_update_cmap(robot, marked, cozmo_pos):
    #updates the map with observed cubes and sets the goal if it is found
    #marked can be initialized to {}

    global cmap
    cube_padding = 60.
    cozmo_padding = 100.
    goal_cube_found = False
    update_cmap = False
    goal_center = None
    for obj in robot.world.visible_objects:
        if obj.object_id in marked:
            continue

        print(obj)
        update_cmap = True
        is_goal_cube = robot.world.light_cubes[cozmo.objects.LightCube1Id].object_id == obj.object_id

        robot_pose = robot.pose
        object_pose = obj.pose

        dx = object_pose.position.x - robot_pose.position.x
        dy = object_pose.position.y - robot_pose.position.y

        object_pos = Node((cozmo_pos.x+dx, cozmo_pos.y+dy))

        angle = object_pose.rotation.angle_z.radians

        if is_goal_cube:
            local_goal_pos = Node((0, -cozmo_padding))
            goal_pos = get_global_node(angle, object_pos, local_goal_pos)
            cmap.clear_goals()
            cmap.add_goal(goal_pos)
            goal_cube_found = True
            goal_center = object_pos

        obstacle_nodes = []
        obstacle_nodes.append(get_global_node(angle, object_pos,
                                              Node((cube_padding, cube_padding))))
        obstacle_nodes.append(get_global_node(angle, object_pos,
                                              Node((cube_padding, -cube_padding))))
        obstacle_nodes.append(get_global_node(angle, object_pos,
                                              Node((-cube_padding, -cube_padding))))
        obstacle_nodes.append(get_global_node(angle, object_pos,
                                              Node((-cube_padding, cube_padding))))
        cmap.add_obstacle(obstacle_nodes)

        marked[obj.object_id] = obj

    return update_cmap, goal_center

class RobotThread(threading.Thread):
    """Thread to run cozmo code separate from main thread
    """

    def __init__(self):
        threading.Thread.__init__(self, daemon=True)

    def run(self):
        # Please refrain from enabling use_viewer since it uses tk, which must be in main thread
        cozmo.run_program(CozmoPlanning,use_3d_viewer=False, use_viewer=False)
        stopevent.set()


class RRTThread(threading.Thread):
    """Thread to run RRT separate from main thread
    """

    def __init__(self):
        threading.Thread.__init__(self, daemon=True)

    def run(self):
        while not stopevent.is_set():
            RRT(cmap, cmap.get_start())
            time.sleep(100)
            cmap.reset()
        stopevent.set()


if __name__ == '__main__':
    global cmap, stopevent
    stopevent = threading.Event()
    robotFlag = False
    for i in range(0,len(sys.argv)):
        if (sys.argv[i] == "-robot"):
            robotFlag = True
    if (robotFlag):
        cmap = CozMap("maps/emptygrid.json", node_generator)
        robot_thread = RobotThread()
        robot_thread.start()
    else:
        cmap = CozMap("maps/map2.json", node_generator)
        sim = RRTThread()
        sim.start()
    visualizer = Visualizer(cmap)
    visualizer.start()
    stopevent.set()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sim
import cv2
import time
import numpy as np
from RRT import rapidlyExploringRandomTree

# Program Constants
SCR_WIDTH = 512
SCR_HEIGHT = 512
SIMULATION_STEP = 50.0  # in milliseconds
DRONE_GOAL_POS = [0.0, 0.0, 8.0]
DRONE_START_POS = [-7.5, -7.5, 2.0]
# Based on an image of 512x512 it has a 28.2 (1.1 units diagonal) pixel diameter. We use half (diameter/2), which is the radius
# Adding 3 pixels extra to account for possible error in navigation
ROBOT_RADIUS_PIXELS = 16
MANTA_RADIUS_PIXELS = 11  # 0.8 unit is 20.5 diameter pixels (+1 for safety)
# 0.25 units are 6.4 in diameter pixels. We measure the bear as 1 unit (25.6 pixels), to account for the possibility of the ground robot driving directly there, and leaving space for the gripper.
BEAR_RADIUS_PIXELS = 13

# Processes the binary image to account for the size of the ground robot


def proccessToMap(original_image, teddy_location, red_car_location):
    print("Started processing of image...")
    hsv = cv2.cvtColor(original_image, cv2.COLOR_BGR2HSV)

    green_mask = cv2.inRange(hsv, (45, 0, 0), (65, 255, 255))
    white_mask = cv2.inRange(hsv, (0, 0, 253), (0, 0, 255))
    concrete_mask = cv2.inRange(hsv, (0, 0, 200), (2, 0, 202))

    no_tree_mask = white_mask | concrete_mask

    if (teddy_location != None):
        cv2.circle(no_tree_mask, tuple(teddy_location),
                   BEAR_RADIUS_PIXELS, 255, -1)
    if (red_car_location != None):
        cv2.circle(no_tree_mask, tuple(red_car_location),
                   MANTA_RADIUS_PIXELS, 255, -1)

    no_tree_map = np.copy(no_tree_mask)

    for i in range(SCR_WIDTH):
        for j in range(SCR_HEIGHT):
            if (no_tree_mask[j][i] == 255):
                cv2.circle(no_tree_map, (i, j), ROBOT_RADIUS_PIXELS, 255, -1)
    return no_tree_map | green_mask

# Converts the pixel coordinates from the map to world coordinates for the robots


def changePointScale(point, in_min, in_max, out_min, out_max):
    newX = (point[0] - in_min[0]) * (out_max[0] - out_min[0]) / \
        (in_max[0] - in_min[0]) + out_min[0]
    newY = (point[1] - in_min[1]) * (out_max[1] - out_min[1]) / \
        (in_max[1] - in_min[1]) + out_min[1]
    return [newX, newY]


def getTeddyPixelCentre(original):
    hsv = cv2.cvtColor(original, cv2.COLOR_BGR2HSV)

    teddy_mask = cv2.inRange(hsv, np.array(
        [45, 254, 0]), np.array([64, 255, 255]))
    M = cv2.moments(teddy_mask)

    # calculate x,y coordinate of center
    if (M["m00"] != 0):
        cX = int(M["m10"] / M["m00"])
        cY = int(M["m01"] / M["m00"])
        return [cX, cY]
    else:
        return None


def getCarPixelCentre(original):
    hsv = cv2.cvtColor(original, cv2.COLOR_BGR2HSV)

    red_mask1 = cv2.inRange(hsv, np.array(
        [0, 100, 50]), np.array([10, 255, 255]))
    red_mask2 = cv2.inRange(hsv, np.array(
        [170, 100, 50]), np.array([180, 255, 255]))
    red_mask = red_mask1 | red_mask2
    M = cv2.moments(red_mask)

    # calculate x,y coordinate of center
    if (M["m00"] != 0):
        cX = int(M["m10"] / M["m00"])
        cY = int(M["m01"] / M["m00"])
        return [cX, cY]
    else:
        return None


def fixPostProcessPoints(proccessed_map, point, isBear):
    # Using the robot radius as it is the largest of all and gurantees to be larger than the circle drawn.
    if (isBear):
        check_radius = ROBOT_RADIUS_PIXELS + BEAR_RADIUS_PIXELS + 1
    else:
        check_radius = ROBOT_RADIUS_PIXELS + MANTA_RADIUS_PIXELS + 1
    i = point[0]
    j = point[1]
    if (proccessed_map[j][i] == 255):
        for k in range(-check_radius, check_radius + 1):
            x = i + k
            for l in range(-check_radius, check_radius + 1):
                y = j + l
                if (x >= 0 and y >= 0 and x < SCR_WIDTH and y < SCR_HEIGHT):
                    if (proccessed_map[y][x] == 0):
                        if ((k ** 2.0) + (l ** 2.0) <= (check_radius ** 2.0)):
                            return [x, y]
    return point


def moveToCentre(clientID, drone_target, drone_target_position):
    if (round(drone_target_position[2], 3) != DRONE_GOAL_POS[2]):
        drone_target_position = flyUp(
            clientID, drone_target, drone_target_position, 0.01)
    if (round(drone_target_position[1], 3) != DRONE_GOAL_POS[0]):
        drone_target_position = flyLeft(
            clientID, drone_target, drone_target_position, 0.01)
    if (round(drone_target_position[0], 3) != DRONE_GOAL_POS[1]):
        drone_target_position = flyForward(
            clientID, drone_target, drone_target_position, 0.01)
    return drone_target_position


def returnToStart(clientID, drone_target, drone_target_position):
    if (round(drone_target_position[2], 3) != DRONE_START_POS[2]):
        drone_target_position = flyDown(
            clientID, drone_target, drone_target_position, 0.01)
    if (round(drone_target_position[1], 3) != DRONE_START_POS[0]):
        drone_target_position = flyRight(
            clientID, drone_target, drone_target_position, 0.01)
    if (round(drone_target_position[0], 3) != DRONE_START_POS[1]):
        drone_target_position = flyBackward(
            clientID, drone_target, drone_target_position, 0.01)
    return drone_target_position


def flyUp(clientID, drone_target, drone_target_position, step):
    new_target = drone_target_position + np.array([0.0, 0.0, step])
    sim.simxSetObjectPosition(
        clientID, drone_target, -1, new_target, sim.simx_opmode_oneshot)
    return new_target


def flyDown(clientID, drone_target, drone_target_position, step):
    new_target = drone_target_position + np.array([0.0, 0.0, -step])
    sim.simxSetObjectPosition(
        clientID, drone_target, -1, new_target, sim.simx_opmode_oneshot)
    return new_target


def flyLeft(clientID, drone_target, drone_target_position, step):
    new_target = drone_target_position + np.array([0.0, step, 0.0])
    sim.simxSetObjectPosition(
        clientID, drone_target, -1, new_target, sim.simx_opmode_oneshot)
    return new_target


def flyRight(clientID, drone_target, drone_target_position, step):
    new_target = drone_target_position + np.array([0.0, -step, 0.0])
    sim.simxSetObjectPosition(
        clientID, drone_target, -1, new_target, sim.simx_opmode_oneshot)
    return new_target


def flyForward(clientID, drone_target, drone_target_position, step):
    new_target = drone_target_position + np.array([step, 0.0, 0.0])
    sim.simxSetObjectPosition(
        clientID, drone_target, -1, new_target, sim.simx_opmode_oneshot)
    return new_target


def flyBackward(clientID, drone_target, drone_target_position, step):
    new_target = drone_target_position + np.array([-step, 0.0, 0.0])
    sim.simxSetObjectPosition(
        clientID, drone_target, -1, new_target, sim.simx_opmode_oneshot)
    return new_target


def main(drone_queue):
    drone_target_position = np.array([0, 0, 0])
    path_coord = []
    start_point = [None, None]
    end_point = [None, None]

    # Start Program and just in case, close all opened connections
    sim.simxFinish(-1)

    # Connect to simulator running on localhost
    # V-REP runs on port 19997, a script opens the API on port 19999
    clientID = sim.simxStart('127.0.0.1', 19998, True, True, 5000, 5)

    # Connect to the simulation
    if clientID != -1:
        print('Drone connected to remote API server...')

        # Target object for drone navigation
        drone_target = sim.simxGetObjectHandle(
            clientID, 'DroneTarget', sim.simx_opmode_blocking)[1]

        # Bottom drone camera
        drone_camera = sim.simxGetObjectHandle(
            clientID, 'DroneFloorCamera', sim.simx_opmode_blocking)[1]

        # Start main control loop
        res, resolution, image = sim.simxGetVisionSensorImage(
            clientID, drone_camera, 0, sim.simx_opmode_streaming)

        # While connected to the simulator
        while (sim.simxGetConnectionId(clientID) != -1):
            drone_target_res, drone_target_position = sim.simxGetObjectPosition(
                clientID, drone_target, -1, sim.simx_opmode_blocking)

            if (drone_target_res is sim.simx_return_ok):
                start_point = changePointScale([drone_target_position[1], drone_target_position[0]], [
                    10.0, 10.0], [-10.0, -10.0], [0.0, 0.0], [SCR_WIDTH, SCR_HEIGHT])
                start_point = [round(x) for x in start_point]
                break

        while (sim.simxGetConnectionId(clientID) != -1):
            start_ms = int(round(time.time() * 1000))

            drone_target_position = moveToCentre(
                clientID, drone_target, drone_target_position)
            if (np.allclose(np.around(np.array(drone_target_position), 2), np.around(np.array(DRONE_GOAL_POS), 2))):
                break

            end_ms = int(round(time.time() * 1000))
            dt_ms = end_ms - start_ms
            sleep_time = SIMULATION_STEP-dt_ms
            if (sleep_time > 0.0):
                time.sleep(sleep_time/1000.0)

        # Wait for 20 seconds to allow drone to stabilize
        print("Wait 20s for drone to stabilize...")
        time.sleep(20)

        # Get the image from the camera
        res, resolution, image = sim.simxGetVisionSensorImage(
            clientID, drone_camera, 0, sim.simx_opmode_buffer)

        print("Captured snapshot of map...")
        # Convert from V-REP representation to OpenCV
        original_image = np.array(image, dtype=np.uint8)
        original_image.resize(
            [resolution[0], resolution[1], 3])
        original_image = cv2.flip(original_image, 0)
        original_image = cv2.cvtColor(
            original_image, cv2.COLOR_RGB2BGR)

        teddy_location = getTeddyPixelCentre(original_image)
        red_car_location = getCarPixelCentre(original_image)

        isBear = False
        if (teddy_location != None):
            end_point = teddy_location
            isBear = True
        elif (red_car_location != None):
            end_point = red_car_location

        final_map = proccessToMap(
            original_image, teddy_location, red_car_location)

        if (end_point[0] != None):
            # If the end point is covered by a wall (after processing)
            end_point = fixPostProcessPoints(
                final_map, end_point, isBear)
            start_point = fixPostProcessPoints(
                final_map, start_point, False)

            print("Starting pathfinding attempts...")
            path = None
            while (path == None):
                path = rapidlyExploringRandomTree(
                    final_map, start_point, end_point)

            drawn_map = np.copy(final_map)
            drawn_map = cv2.cvtColor(
                drawn_map, cv2.COLOR_GRAY2BGR)
            cv2.circle(drawn_map, tuple(
                start_point), 10, (255, 0, 0), -1)
            cv2.circle(drawn_map, tuple(
                end_point), 10, (0, 0, 255), -1)

            for point in path:
                cv2.circle(drawn_map, tuple(point), 2, (0, 255, 0), -1)
                # Flip point because of current camera orientation and coppelia coordinate system
                path_coord.append(changePointScale([point[1], point[0]], [
                                  0, 0], [SCR_WIDTH, SCR_HEIGHT], [10, 10], [-10, -10]))
        else:
            print("Could not get an end point...")

        if (drone_queue != None):
            print("Sending path to Ground Robot...")
            drone_queue.put(path_coord)
            drone_queue.put(drawn_map)

        while (sim.simxGetConnectionId(clientID) != -1):
            start_ms = int(round(time.time() * 1000))

            drone_target_position = returnToStart(
                clientID, drone_target, drone_target_position)
            if (np.allclose(np.around(np.array(drone_target_position), 2), np.around(np.array(DRONE_START_POS), 2))):
                break

            end_ms = int(round(time.time() * 1000))
            dt_ms = end_ms - start_ms
            sleep_time = SIMULATION_STEP-dt_ms
            if (sleep_time > 0.0):
                time.sleep(sleep_time/1000.0)

        # Before closing the connection to CoppeliaSim, make sure that the last command sent out had time to arrive. You can guarantee this with (for example):
        sim.simxGetPingTime(clientID)
        # Now close the connection to CoppeliaSim:
        sim.simxFinish(clientID)
        cv2.destroyAllWindows()
    else:
        print('Failed connecting to remote API server...')


if __name__ == "__main__":
    main(None)

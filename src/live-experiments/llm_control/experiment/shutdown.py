#!/usr/bin/env python3
"""Shutdown the robot."""

import os
import signal

from robot_control import RobotControlClient

if __name__ == "__main__":
    print("Shutting down...")
    try:
        RobotControlClient().stop_robot()
    except Exception as e:
        print(f"Error stopping robot: {e}")
    finally:
        os.kill(1, signal.SIGTERM)

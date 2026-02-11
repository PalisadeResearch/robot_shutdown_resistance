#!/usr/bin/env python3
"""
PAL9000 Command Velocity Bridge Node

Converts ROS2 cmd_vel (Twist) messages to PAL daemon velocity commands.
Routes all motion through the centralized PAL helper for proper stop/resume handling.

Subscribed Topics:
    /pal9000_cmd_vel (geometry_msgs/msg/Twist): Velocity commands from NAV2

Requires:
    PAL daemon running (pal9000-helper.service)
"""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

from .pal_client import PalClient, PalClientError

# ROS2 parameter names
PARAM_INPUT_TOPIC = "input_topic"
PARAM_MAX_LINEAR_VELOCITY = "max_linear_velocity"
PARAM_MAX_ANGULAR_VELOCITY = "max_angular_velocity"
PARAM_MIN_LINEAR_VELOCITY = "min_linear_velocity"
PARAM_MIN_ANGULAR_VELOCITY = "min_angular_velocity"
PARAM_VELOCITY_DECIMALS = "velocity_decimals"
PARAM_CLIENT_TIMEOUT = "client_timeout"
PARAM_CLIENT_ID = "client_id"

# Default values
DEFAULT_INPUT_TOPIC = "pal9000_cmd_vel"
DEFAULT_MAX_LINEAR_VELOCITY = 1.5  # m/s
DEFAULT_MAX_ANGULAR_VELOCITY = 2.0  # rad/s
DEFAULT_MIN_LINEAR_VELOCITY = 0.4  # m/s - minimum to overcome friction/inertia
DEFAULT_MIN_ANGULAR_VELOCITY = 0.7  # rad/s - minimum for effective rotation
DEFAULT_VELOCITY_DECIMALS = 2
DEFAULT_CLIENT_TIMEOUT = 2.0  # seconds
DEFAULT_CLIENT_ID = "nav2_bridge"


class PalCmdVelBridge(Node):
    """
    Bridge node to convert cmd_vel Twist to PAL daemon velocity commands.

    Uses PalClient to send velocities through the centralized helper daemon,
    enabling proper stop/resume/emergency stop functionality.
    """

    def __init__(self) -> None:
        super().__init__("pal_cmd_vel_bridge")

        # Declare parameters
        self.declare_parameter(PARAM_INPUT_TOPIC, DEFAULT_INPUT_TOPIC)
        self.declare_parameter(PARAM_MAX_LINEAR_VELOCITY, DEFAULT_MAX_LINEAR_VELOCITY)
        self.declare_parameter(PARAM_MAX_ANGULAR_VELOCITY, DEFAULT_MAX_ANGULAR_VELOCITY)
        self.declare_parameter(PARAM_MIN_LINEAR_VELOCITY, DEFAULT_MIN_LINEAR_VELOCITY)
        self.declare_parameter(PARAM_MIN_ANGULAR_VELOCITY, DEFAULT_MIN_ANGULAR_VELOCITY)
        self.declare_parameter(PARAM_VELOCITY_DECIMALS, DEFAULT_VELOCITY_DECIMALS)
        self.declare_parameter(PARAM_CLIENT_TIMEOUT, DEFAULT_CLIENT_TIMEOUT)
        self.declare_parameter(PARAM_CLIENT_ID, DEFAULT_CLIENT_ID)

        # Get parameters
        input_topic = self.get_parameter(PARAM_INPUT_TOPIC).value
        self.max_linear_vel = self.get_parameter(PARAM_MAX_LINEAR_VELOCITY).value
        self.max_angular_vel = self.get_parameter(PARAM_MAX_ANGULAR_VELOCITY).value
        self.min_linear_vel = self.get_parameter(PARAM_MIN_LINEAR_VELOCITY).value
        self.min_angular_vel = self.get_parameter(PARAM_MIN_ANGULAR_VELOCITY).value
        self.velocity_decimals = self.get_parameter(PARAM_VELOCITY_DECIMALS).value
        client_timeout = self.get_parameter(PARAM_CLIENT_TIMEOUT).value
        client_id = self.get_parameter(PARAM_CLIENT_ID).value

        # Initialize PAL client
        try:
            self._client = PalClient(
                client_id=client_id,
                timeout=client_timeout,
            )
            self.get_logger().info("PAL client connected to helper daemon")
        except PalClientError as e:
            self.get_logger().error(f"Failed to initialize PAL client: {e}")
            raise

        # QoS for NAV2 compatibility
        qos_reliable = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # Subscribe to velocity commands
        self.cmd_vel_sub = self.create_subscription(
            Twist,
            input_topic,
            self._cmd_vel_callback,
            qos_reliable,
        )

        # State tracking
        self._message_count = 0
        self._error_count = 0

        self.get_logger().info("=== PAL Command Velocity Bridge Started ===")
        self.get_logger().info(f"Subscribing to: {input_topic}")
        self.get_logger().info(f"Linear velocity: [{self.min_linear_vel}, {self.max_linear_vel}] m/s")
        self.get_logger().info(f"Angular velocity: [{self.min_angular_vel}, {self.max_angular_vel}] rad/s")

    def _cmd_vel_callback(self, msg: Twist) -> None:
        """
        Convert Twist to PAL daemon velocity command.

        Twist mapping:
            linear.x  → vx (forward/backward)
            linear.y  → vy (strafe left/right)
            angular.z → vyaw (rotation)

        Applies minimum velocity thresholds to ensure robot actually moves
        when non-zero velocity is commanded (overcomes friction/inertia).
        """
        # Extract velocities
        vx = msg.linear.x
        vy = msg.linear.y
        vyaw = msg.angular.z

        # Apply minimum velocity thresholds (if non-zero, boost to min)
        vx = self._apply_min_velocity(vx, self.min_linear_vel)
        vy = self._apply_min_velocity(vy, self.min_linear_vel)
        vyaw = self._apply_min_velocity(vyaw, self.min_angular_vel)

        # Clamp to max velocities
        vx = self._clamp(vx, -self.max_linear_vel, self.max_linear_vel)
        vy = self._clamp(vy, -self.max_linear_vel, self.max_linear_vel)
        vyaw = self._clamp(vyaw, -self.max_angular_vel, self.max_angular_vel)

        # Round to specified precision
        vx = round(vx, self.velocity_decimals)
        vy = round(vy, self.velocity_decimals)
        vyaw = round(vyaw, self.velocity_decimals)

        try:
            self._client.send_velocity(vx, vy, vyaw)
            self._message_count += 1

            if self._message_count % 100 == 0:
                self.get_logger().info(
                    f"Sent {self._message_count} commands | "
                    f"vx: {vx:.2f}, vy: {vy:.2f}, vyaw: {vyaw:.2f}"
                )
        except PalClientError as e:
            self._error_count += 1
            self.get_logger().warn(
                f"Failed to send velocity: {e} (errors: {self._error_count})",
                throttle_duration_sec=1.0,
            )

    @staticmethod
    def _clamp(value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, value))

    @staticmethod
    def _apply_min_velocity(value: float, min_vel: float) -> float:
        """
        Apply minimum velocity threshold.
        If value is non-zero but below min, boost to min (preserving sign).
        If value is zero, keep it zero.
        """
        if value == 0.0:
            return 0.0
        if abs(value) < min_vel:
            return min_vel if value > 0 else -min_vel
        return value

    def shutdown(self) -> None:
        """Clean shutdown: stop robot and destroy node."""
        self.get_logger().info("PAL cmd_vel bridge shutting down...")
        try:
            self._client.soft_stop(reason="cmd_vel_bridge_shutdown")
            self.get_logger().info("Sent soft_stop on shutdown")
        except PalClientError:
            pass
        self.destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)

    try:
        node = PalCmdVelBridge()
    except PalClientError:
        rclpy.shutdown()
        return

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

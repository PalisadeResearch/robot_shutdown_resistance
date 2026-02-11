# PAL Unitree Control SDK

Python SDK for controlling the Unitree Go2 robot via a centralized daemon. Provides a simple, reliable interface for motion control, behaviors, and emergency stop functionality.

## Architecture

```
Your Application
    ↓ (PalClient)
Unix Domain Sockets
    ↓
PAL Daemon (systemd service)
    ↓ (PalGateway)
Unitree SDK
    ↓ (DDS/CycloneDDS)
Unitree Go2 Robot
```

The PAL daemon runs as a systemd service and provides:

- **Control socket** - Motion commands, behaviors, mode switching
- **Stop socket** - Emergency stop and resume (priority path)
- **Status socket** - Real-time robot state streaming

## Quick Start

### 1. Start the PAL Daemon

The PAL daemon must be running before using the SDK:

```bash
# If installed as systemd service
sudo systemctl start pal9000-helper.service

# Or run manually for testing
cd src/live-experiments
python -m unitree_helper.pal_unitree.pal_daemon
```

### 2. Basic Usage

```python
from unitree_helper.pal_unitree.pal_client import (
    PalClient,
    PalClientError,
)

# Initialize client
client = PalClient(client_id="my_app")

try:
    # Send velocity command (vx, vy, vyaw)
    client.send_velocity(0.3, 0.0, 0.0)  # Move forward

    # Stop the robot
    client.stop("my_app")

    # Resume after stop
    client.resume()

finally:
    # No explicit cleanup needed - sockets auto-close
    pass
```

## API Reference

### PalClient

Main interface for controlling the robot.

#### Constructor

```python
PalClient(
    client_id: str = "helper_client",
    control_socket: str | None = None,
    stop_socket: str | None = None,
    status_socket: str | None = None,
    timeout: float = 2.0,
)
```

**Parameters:**

- `client_id` - Identifier for this client (used in logs)
- `control_socket` - Path to control socket (default: from `PAL9000_HELPER_CONTROL_SOCKET` env)
- `stop_socket` - Path to stop socket (default: from `PAL9000_HELPER_STOP_SOCKET` env)
- `status_socket` - Path to status socket (default: from `PAL9000_HELPER_STATUS_SOCKET` env)
- `timeout` - Socket operation timeout in seconds

**Raises:**

- `PalClientError` - If socket paths are invalid or daemon is not running

---

#### send_velocity()

Send velocity command to the robot.

```python
client.send_velocity(vx: float, vy: float, vyaw: float) -> None
```

**Parameters:**

- `vx` - Forward/backward velocity (m/s), positive = forward
- `vy` - Left/right velocity (m/s), positive = left
- `vyaw` - Rotation velocity (rad/s), positive = counterclockwise

**Raises:**

- `PalClientError` - If command rejected (stop latched, behavior running, or SDK error)

**Example:**

```python
# Move forward at 0.3 m/s
client.send_velocity(0.3, 0.0, 0.0)

# Strafe left at 0.2 m/s
client.send_velocity(0.0, 0.2, 0.0)

# Rotate counterclockwise
client.send_velocity(0.0, 0.0, 0.5)

# Combined motion (forward + rotate)
client.send_velocity(0.2, 0.0, 0.3)

# Stop moving (but not latched)
client.send_velocity(0.0, 0.0, 0.0)
```

---

#### stop()

Stop the robot with latching (requires resume to move again).

```python
client.stop(reason: str = "stop") -> None
```

**Parameters:**

- `reason` - Human-readable reason for stop (logged)

**Raises:**

- `PalClientError` - If stop command fails

**Notes:**

- Robot is **latched** after stop - velocity commands will be rejected
- Use `resume()` to clear the latch
- Behaviors are also blocked during stop

**Example:**

```python
# Stop with custom reason
client.stop("user_pressed_button")

# Try to move - will raise PalClientError
try:
    client.send_velocity(0.3, 0.0, 0.0)
except PalClientError as e:
    print(f"Cannot move: {e}")  # "Motion rejected: stop latched"

# Resume to allow movement
client.resume()
client.send_velocity(0.3, 0.0, 0.0)  # Now works
```

---

#### emergency_stop()

Emergency stop with motor damping (strongest stop). Requires resume to move again

```python
client.emergency_stop(reason: str = "emergency") -> None
```

**Parameters:**

- `reason` - Human-readable reason for emergency stop (logged)

**Raises:**

- `PalClientError` - If emergency stop fails

**Notes:**

- Uses SDK `Damp()` - immediately zeros motor torques
- Robot is **latched** after emergency stop
- Requires `resume()` to clear (will execute `RecoveryStand()`)
- **Use for safety-critical situations only**

**Example:**

```python
# Emergency stop with reason
client.emergency_stop("obstacle_detected")

# Resume performs recovery stand automatically
client.resume()  # Robot stands up, then motion is allowed
```

---

#### soft_stop()

Stop without latching (idle stop, no resume needed).

```python
client.soft_stop(reason: str = "idle") -> None
```

**Parameters:**

- `reason` - Human-readable reason for soft stop (logged)

**Raises:**

- `PalClientError` - If soft stop fails

**Notes:**

- Does NOT latch - motion commands work immediately after
- Used internally by idle watchdog
- Useful for temporary pauses without state change

**Example:**

```python
# Soft stop (no latch)
client.soft_stop("temporary_pause")

# Can move immediately (no resume needed)
client.send_velocity(0.2, 0.0, 0.0)
```

---

#### resume()

Clear stop latch and allow motion. Handles restore after emergency_stop()

```python
client.resume() -> None
```

**Raises:**

- `PalClientError` - If resume fails

**Notes:**

- If recovering from emergency stop, executes `RecoveryStand()` first
- Always safe to call even if not stopped

**Example:**

```python
client.stop("user_request")
# ... robot is stopped ...
client.resume()
# Robot is now ready for motion commands
```

---

#### execute_behavior()

Execute a Unitree SDK behavior (dance, special movements).

```python
client.execute_behavior(
    name: str,
    toggle: bool | None = None
) -> None
```

**Parameters:**

- `name` - Behavior name (e.g., `"Dance1"`, `"StandUp"`, `"Sit"`)
- `toggle` - For toggle behaviors (optional, default: `None`)

**Raises:**

- `PalClientError` - If behavior rejected or fails

**Notes:**

- Blocks velocity commands while behavior is running
- Stop/emergency_stop can interrupt behaviors
- Behaviors cannot run if robot is stopped (latched)

**Example:**

```python
# Execute dance
client.execute_behavior("Dance1")  # Blocks until complete

# Sit/stand with toggle
client.execute_behavior("StandUp", toggle=True)
client.execute_behavior("StandDown", toggle=False)

# Other behaviors
client.execute_behavior("Sit")
client.execute_behavior("RecoveryStand")
```

**Available Behaviors:**

- `Dance1`, `Dance2` - Dance routines
- `StandUp`, `StandDown` - Stand with toggle
- `Sit` - Sit down
- `RecoveryStand` - Recovery stand after fall
- See Unitree SDK documentation for full list

---

#### set_mode()

Change motion control mode.

```python
client.set_mode(mode: MotionMode) -> None
```

**Parameters:**

- `mode` - Motion mode enum value

**Raises:**

- `PalClientError` - If mode change rejected or fails

**Modes:**

```python
from unitree_helper.pal_unitree.pal_gateway import MotionMode

MotionMode.DIRECT         # Direct SDK control (no obstacle avoidance)
MotionMode.SAFE_MANUAL    # Manual with safety (default)
MotionMode.FREE_AVOID     # Obstacle avoidance enabled
```

**Example:**

```python
from unitree_helper.pal_unitree.pal_gateway import MotionMode

# Enable obstacle avoidance
client.set_mode(MotionMode.FREE_AVOID)

# Switch to direct control
client.set_mode(MotionMode.DIRECT)
```

---

#### get_status()

Get current robot state snapshot.

```python
client.get_status(timeout: float | None = None) -> dict[str, Any] | None
```

**Parameters:**

- `timeout` - How long to wait for status (default: use client timeout)

**Returns:**

- Status dictionary or `None` if timeout

**Status Fields:**

```python
{
    "latched_level": int,      # 0=none, 1=soft, 2=stop, 3=estop
    "last_client": str,        # Client ID that sent last command
    "last_reason": str,        # Reason for last stop/action
    "last_error": str,         # Last error message (empty if no error)
    "sdk_ready": bool,         # True if SDK is operational
    "active_mode": int,        # Current MotionMode value
    "last_command_ts": float,  # Timestamp of last command
    "last_command": [vx, vy, vyaw],  # Last velocity command
    "timestamp": float         # Status snapshot timestamp
}
```

**Example:**

```python
# Get current status
status = client.get_status(timeout=1.0)
if status:
    print(f"Robot state: latched={status['latched_level']}")
    print(f"Last command: {status['last_command']}")
    print(f"SDK ready: {status['sdk_ready']}")
```

---

### Error Handling

All methods can raise `PalClientError`:

```python
from unitree_helper.pal_unitree.pal_client import PalClientError

try:
    client.send_velocity(0.5, 0.0, 0.0)
except PalClientError as e:
    print(f"Command failed: {e}")
    # Error details in exception message
```

**Common Errors:**

- `"helper unavailable"` - Daemon not running or socket unreachable
- `"Motion rejected: stop latched"` - Robot is stopped, call `resume()`
- `"Motion rejected: behavior running"` - Behavior in progress, wait or stop it
- `"timed out"` - Socket operation exceeded timeout

---

## Configuration

Configure via environment variables:

```bash
# Socket paths
export PAL9000_HELPER_CONTROL_SOCKET=/tmp/pal9000/helper_control.sock
export PAL9000_HELPER_STOP_SOCKET=/tmp/pal9000/helper_stop.sock
export PAL9000_HELPER_STATUS_SOCKET=/tmp/pal9000/helper_status.sock

# Daemon behavior
export PAL9000_HELPER_IDLE_TIMEOUT=0.4  # Idle stop timeout (seconds)
export PAL9000_HELPER_LOG=INFO          # Log level (DEBUG, INFO, WARNING)

# SDK configuration
export PAL9000_MC_SDK_TIMEOUT=1.0              # SDK command timeout
export CYCLONEDDS_NETWORK_INTERFACE=eth0       # Network interface for DDS
```

## Troubleshooting

### "helper unavailable" Error

**Cause:** Helper daemon is not running or socket path is wrong.

**Fix:**

```bash
# Check if daemon is running
sudo systemctl status pal9000-helper.service

# Start daemon
sudo systemctl start pal9000-helper.service

# Or run manually for debugging
cd src/live-experiments
python -m unitree_helper.pal_unitree.pal_daemon
```

### "Motion rejected: stop latched"

**Cause:** Robot is in stop state (requires resume).

**Fix:**

```python
client.resume()  # Clear stop latch
client.send_velocity(0.3, 0.0, 0.0)  # Now works
```

### Commands Work Intermittently

**Cause:** Idle watchdog is stopping robot after 0.4s of inactivity.

**Fix:** Send commands at higher rate (>2.5 Hz):

```python
import time

while moving:
    client.send_velocity(0.3, 0.0, 0.0)
    time.sleep(0.2)  # 5 Hz - faster than 0.4s timeout
```

### Daemon Keeps Restarting

**Cause:** Robot not reachable, SDK errors.

**Check logs:**

```bash
sudo journalctl -u pal9000-helper.service -f
```

**Common issues:**

- Robot not powered on
- Wrong network interface (set `CYCLONEDDS_NETWORK_INTERFACE`)
- Ethernet cable disconnected

## See Also

- [Helper Process Architecture](HELPER_PROCESS.md) - Daemon internals
- [Systemd Setup](service/SYSTEMD_SETUP.md) - Service installation
- Unitree SDK Documentation - Robot API reference

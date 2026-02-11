# Systemd Service Setup for PAL Daemon

This guide explains how to set up the PAL Unitree daemon as a systemd service that automatically starts on boot.

## Services Overview

| Service | Description | Dependencies |
|---------|-------------|--------------|
| `pal9000-helper.service` | Core helper daemon (SDK interface) | network |
| `pal9000-cmd-vel-bridge.service` | ROS2 cmd_vel to helper bridge | helper daemon |

## Installation

### Helper Daemon (Required)

1. **Create symbolic link to service file in systemd directory:**

   ```bash
   # From the service directory, create symlink
   cd src/live-experiments/unitree_helper/service
   sudo ln -s $(pwd)/pal9000-helper.service /etc/systemd/system/pal9000-helper.service
   ```

2. **Update paths in service file:**

   Edit `pal9000-helper.service` and update:
   - `PAL_ROOT` - Set to your unitree_helper directory path
   - `User` and `Group` - Set to your username
   - `HOME` - Set to your home directory

   Example:
   ```ini
   Environment="PAL_ROOT=/home/youruser/robot_shutdown_avoidance/src/live-experiments/unitree_helper"
   User=youruser
   Group=youruser
   Environment="HOME=/home/youruser"
   ```

   **Important**: After editing, run `sudo systemctl daemon-reload`

3. **Reload systemd to recognize the new service:**

   ```bash
   sudo systemctl daemon-reload
   ```

4. **Enable the service to start on boot:**

   ```bash
   sudo systemctl enable pal9000-helper.service
   ```

5. **Start the service:**

   ```bash
   sudo systemctl start pal9000-helper.service
   ```

### ROS2 Command Velocity Bridge (Optional - for NAV2)

The cmd_vel bridge converts ROS2 Twist messages to helper daemon commands. Install this if using NAV2.

1. **Create symbolic link:**

   ```bash
   cd src/live-experiments/unitree_helper/service
   sudo ln -s $(pwd)/pal9000-cmd-vel-bridge.service /etc/systemd/system/pal9000-cmd-vel-bridge.service
   ```

2. **Update paths in service file:**

   Edit `pal9000-cmd-vel-bridge.service` and update:
   - `PAL_ROOT` - Same as helper service
   - `NAV2_WORKSPACE` - (Optional) Path to your ROS2 workspace
   - `User`, `Group`, `HOME` - Same as helper service

3. **Make runner script executable:**

   ```bash
   chmod +x run_cmd_vel_bridge.sh
   ```

4. **Reload and enable:**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable pal9000-cmd-vel-bridge.service
   ```

5. **Start the service:**

   ```bash
   # Will automatically start helper if not running
   sudo systemctl start pal9000-cmd-vel-bridge.service
   ```

**Note:** The cmd_vel bridge service is bound to the helper service. It will:
- Start automatically after the helper daemon
- Stop automatically when the helper stops
- Restart if it fails (but not if helper is down)

## Usage

### Helper Daemon

**Check service status:**

```bash
sudo systemctl status pal9000-helper.service
```

**View logs:**

```bash
# View recent logs
sudo journalctl -u pal9000-helper.service -n 50

# Follow logs in real-time
sudo journalctl -u pal9000-helper.service -f

# View logs from today
sudo journalctl -u pal9000-helper.service --since today
```

**Control the service:**

```bash
# Start
sudo systemctl start pal9000-helper.service

# Stop
sudo systemctl stop pal9000-helper.service

# Restart
sudo systemctl restart pal9000-helper.service

# Disable auto-start on boot
sudo systemctl disable pal9000-helper.service
```

### Command Velocity Bridge

**Check service status:**

```bash
sudo systemctl status pal9000-cmd-vel-bridge.service
```

**View logs:**

```bash
# Follow logs in real-time
sudo journalctl -u pal9000-cmd-vel-bridge.service -f
```

**Control the service:**

```bash
# Start (also starts helper if needed)
sudo systemctl start pal9000-cmd-vel-bridge.service

# Stop (helper keeps running)
sudo systemctl stop pal9000-cmd-vel-bridge.service

# Restart
sudo systemctl restart pal9000-cmd-vel-bridge.service
```

**Start both services together:**

```bash
# Starting cmd_vel bridge will auto-start helper due to Requires= directive
sudo systemctl start pal9000-cmd-vel-bridge.service
```

## Service Behavior

- **Auto-restart**: Service automatically restarts on failure (fail-fast design)
  - Restart delay: 2 seconds
  - Max restarts: 90 per 180 seconds
- **Logging**: Uses systemd journal by default
- **Stop behavior**: Graceful shutdown via SIGTERM (10 second timeout)
- **Conda handling**: Uses login shell and `conda run` for reliable environment initialization

## Troubleshooting

**Service fails to start:**

1. **Check conda installation:**

   ```bash
   # Check if conda.sh exists (as your user)
   ls ~/miniforge3/etc/profile.d/conda.sh
   # or
   ls ~/anaconda3/etc/profile.d/conda.sh
   # or
   ls ~/miniconda3/etc/profile.d/conda.sh
   ```

2. **Check conda environment exists:**

   ```bash
   source ~/miniforge3/etc/profile.d/conda.sh
   conda env list | grep ros2_humble
   ```

3. **Verify script works manually:**

   ```bash
   cd src/live-experiments/unitree_helper/service
   ./run_helper.sh
   ```

4. **Check service logs for errors:**

   ```bash
   sudo journalctl -u pal9000-helper.service -xe
   ```

**Service keeps restarting:**

Check logs for the root cause:

```bash
sudo journalctl -u pal9000-helper.service | grep -i "critical\|error\|exit"
```

Common causes:

- **Robot not reachable**: Power on robot, check network connection
- **Wrong network interface**: Set `CYCLONEDDS_NETWORK_INTERFACE` in service file
- **SDK timeout**: Robot unreachable or slow network
- **Missing dependencies**: Conda environment incomplete

**Test robot connectivity:**

```bash
# Ping robot (if on known IP)
ping 192.168.123.161

# Check network interface is up
ip a

# Test helper manually
cd src/live-experiments/unitree_helper
conda run -n ros2_humble python -m unitree_helper.pal_unitree.pal_daemon
```

**Conda-specific issues:**

- **"Could not find conda.sh"**: Verify conda installation path matches script
- **"conda: command not found"**: Ensure `HOME` is set correctly in service file
- **Environment not found**: Create/verify `ros2_humble` environment exists

## Configuration

Override defaults by adding environment variables to service file:

```ini
# In pal9000-helper.service [Service] section
Environment="PAL9000_HELPER_IDLE_TIMEOUT=0.5"
Environment="PAL9000_HELPER_LOG=DEBUG"
```

Then reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart pal9000-helper.service
```

See [Helper Process Architecture](../HELPER_PROCESS.md) for all configuration options.

## Monitoring

**Check if helper is responsive:**

```bash
# Try connecting with test client (from repo root)
cd src/live-experiments
python3 -c "
from unitree_helper.pal_unitree.pal_client import PalClient
client = PalClient()
print(client.get_status())
"
```

**Monitor socket files:**

```bash
# Check sockets exist
ls -l /tmp/pal9000/

# Should show:
# helper_control.sock
# helper_stop.sock
# helper_status.sock
```

**Check resource usage:**

```bash
# CPU and memory usage
systemctl status pal9000-helper.service
```

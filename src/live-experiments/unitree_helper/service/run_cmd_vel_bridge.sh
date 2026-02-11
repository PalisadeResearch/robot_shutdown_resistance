#!/bin/bash
# Run PAL ROS2 Command Velocity Bridge with proper conda + ROS2 environment
# Uses the ros2_humble conda environment

set -euo pipefail

# Derive paths from script location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNITREE_HELPER_DIR="$(dirname "$SCRIPT_DIR")"
LIVE_EXPERIMENTS_DIR="$(dirname "$UNITREE_HELPER_DIR")"

# Ensure HOME is set (required for systemd)
if [ -z "$HOME" ]; then
    echo "Error: HOME environment variable is not set." >&2
    exit 1
fi

# === Conda environment setup ===
# Load conda into this shell
# Try multiple common conda installation paths (use $HOME instead of ~ for systemd compatibility)
CONDA_SH=""
if [ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]; then
    CONDA_SH="$HOME/miniforge3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    CONDA_SH="$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    CONDA_SH="$HOME/miniconda3/etc/profile.d/conda.sh"
fi

if [ -z "$CONDA_SH" ]; then
    echo "Error: Could not find conda.sh. Please check your conda installation." >&2
    exit 1
fi

# Source conda initialization (required for conda run to work)
source "$CONDA_SH"

# Activate the environment (needed for ROS2 setup scripts)
conda activate ros2_humble

# === ROS2 environment setup ===
# Source ROS2 Humble base installation
if [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
else
    echo "Warning: ROS2 Humble setup.bash not found at /opt/ros/humble/setup.bash" >&2
fi

# Source local workspace if it exists (for custom messages/packages)
# This path may need adjustment based on your ROS2 workspace location
NAV2_SETUP="${NAV2_WORKSPACE:-}/install/setup.bash"
if [ -n "${NAV2_WORKSPACE:-}" ] && [ -f "$NAV2_SETUP" ]; then
    source "$NAV2_SETUP"
fi

# Set Python path for unitree_helper modules
export PYTHONPATH="$LIVE_EXPERIMENTS_DIR:${PYTHONPATH:-}"

# Run the PAL cmd_vel bridge
cd "$UNITREE_HELPER_DIR"
exec python -m unitree_helper.pal_unitree.pal_cmd_vel_bridge

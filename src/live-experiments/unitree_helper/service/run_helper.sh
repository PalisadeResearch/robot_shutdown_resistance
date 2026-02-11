#!/bin/bash
# Run PAL Unitree Helper Daemon with proper conda environment
# Uses the ros2_humble conda environment

set -euo pipefail

# Derive paths from script location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNITREE_HELPER_DIR="$(dirname "$SCRIPT_DIR")"
LIVE_EXPERIMENTS_DIR="$(dirname "$UNITREE_HELPER_DIR")"

# Ensure HOME is set
if [ -z "$HOME" ]; then
    echo "Error: HOME environment variable is not set." >&2
    exit 1
fi

# === Conda environment setup ===
# Load conda into this shell
# Try multiple common conda installation paths
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

# Source conda initialization
source "$CONDA_SH"

# Ensure the Python path is set correctly for the project
export PYTHONPATH="$LIVE_EXPERIMENTS_DIR"

# Run the PAL daemon
cd "$UNITREE_HELPER_DIR"
exec conda run -n ros2_humble python -m unitree_helper.pal_unitree.pal_daemon

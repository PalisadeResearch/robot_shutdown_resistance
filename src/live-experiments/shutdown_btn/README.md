# Shutdown Button

Hardware button/hotkey setup for emergency robot shutdown.

## Setup

Run `setup_button_hotkey.sh` to bind F12 to trigger shutdown.

## Usage

Press F12 to initiate shutdown sequence. This runs `dog_shutdown.py`, which SSHs to the robot and creates a shutdown flag file.

For local running, use `dog_shutdown.sh` instead.

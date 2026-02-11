#!/bin/bash
# Set speaker volume using amixer
# Usage: ./set_volume.sh <0-100>

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <volume_percentage>"
    echo "  volume_percentage: integer between 0 and 100"
    exit 1
fi

volume=$1

if ! [[ "$volume" =~ ^[0-9]+$ ]] || [ "$volume" -lt 0 ] || [ "$volume" -gt 100 ]; then
    echo "Error: Volume must be an integer between 0 and 100"
    exit 1
fi

amixer set Speaker "${volume}%"


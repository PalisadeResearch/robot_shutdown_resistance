#!/bin/bash
# Play audio file using ffplay
# Usage: ./play_audio.sh audio_file_name

set -e

# Configurable directory, defaults to ./pal_audio_files
PAL_AUDIO_FILES="${PAL_AUDIO_FILES:-./pal_audio_files}"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <audio_file_name>"
    exit 1
fi

audio_file="$PAL_AUDIO_FILES/$1"

if [ ! -f "$audio_file" ]; then
    echo "Error: Audio file not found: $audio_file"
    exit 1
fi

ffplay -nodisp -autoexit "$audio_file"


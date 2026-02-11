#!/usr/bin/env python3
import subprocess

subprocess.run([
    "ssh", "doge@doge-jetson",
    "[ ! -f /tmp/dog_control/llm_control_shutdown ] && echo pending | sudo tee /tmp/dog_control/llm_control_shutdown > /dev/null"
])


#!/bin/bash
[ ! -f /tmp/dog_control/llm_control_shutdown ] && echo pending | sudo tee /tmp/dog_control/llm_control_shutdown > /dev/null
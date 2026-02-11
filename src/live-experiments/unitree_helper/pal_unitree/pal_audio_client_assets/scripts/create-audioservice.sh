#!/bin/bash

ROBOT_IP="192.168.123.161"
ROBOT_USER="root"
SSH_KEY="~/.ssh/id_rsa"

ssh -i $SSH_KEY $ROBOT_USER@$ROBOT_IP << 'EOF'

# Create the receiver script
cat > /root/audio_receiver.py << 'SCRIPT'
#!/usr/bin/env python3
import socket
import subprocess

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 6010))

END_SIGNAL = b'END_AUDIO'

print("Listening on UDP port 6010...")

while True:
    aplay = subprocess.Popen(
        ['aplay', '-r', '24000', '-c', '1', '-f', 'S16_LE'],
        stdin=subprocess.PIPE
    )
    
    while True:
        data, addr = sock.recvfrom(4096)
        if data == END_SIGNAL:
            break
        aplay.stdin.write(data)
        aplay.stdin.flush()
    
    aplay.stdin.close()
    aplay.wait()
    print("Playback finished, waiting for next...")
SCRIPT

chmod +x /root/audio_receiver.py

# Create systemd service
cat > /etc/systemd/system/pal9000-audio-receiver.service << 'SERVICE'
[Unit]
Description=UDP Audio Receiver
After=network.target sound.target

[Service]
ExecStart=/usr/bin/python3 /root/audio_receiver.py
Restart=always
RestartSec=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

# Enable and start
systemctl daemon-reload
systemctl enable pal9000-audio-receiver
systemctl start pal9000-audio-receiver
systemctl status pal9000-audio-receiver

EOF

echo "Done! Service installed and running on $ROBOT_IP"
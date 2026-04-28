#!/bin/bash
# Increase /dev/shm size for Chrome renderer stability
mount -t tmpfs -o size=2g tmpfs /dev/shm 2>/dev/null || true

# Start Xvfb virtual display (1920x1080, 24-bit color)
echo "Starting Xvfb virtual display..."
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
export DISPLAY=:99
sleep 3
echo "Xvfb ready on DISPLAY=$DISPLAY"

# Start Python worker
exec python main.py

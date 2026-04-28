#!/bin/bash
# Start Xvfb virtual display — gives Chrome a real screen to render on
# This is what makes the portal work on the server exactly like on your PC

echo "Starting Xvfb virtual display on :99 ..."
Xvfb :99 -screen 0 1920x1080x24 -ac &
export DISPLAY=:99

# Wait for Xvfb to be ready
sleep 2
echo "Xvfb started. DISPLAY=$DISPLAY"

# Start the Python worker
exec python main.py

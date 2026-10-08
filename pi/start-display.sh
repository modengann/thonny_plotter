#!/bin/bash
# Start the virtual screen :1, a window manager, then the dashboard on it.
# Run by plotter-display.service.  When the dashboard closes, this script
# ends and systemd starts it all again.
set -e
export DISPLAY=:1
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1        # left over from a crash
Xvfb :1 -screen 0 1280x800x24 -nolisten tcp &
for i in $(seq 50); do
    xdpyinfo >/dev/null 2>&1 && break
    sleep 0.1
done
openbox &
xhost +SI:localuser:plotstudent >/dev/null   # student programs draw here
cd "$(dirname "$0")/.."
exec python3 dashboard.py --kiosk

#!/bin/bash
# One-time (and update) setup of the AX4 plotter on a Raspberry Pi.
# Copy the project folder to the Pi, then from inside it run:
#     sudo bash pi/setup.sh
# Safe to run again after copying a newer version: it keeps the Pi's
# plotter_config.json and the uploads.
set -euo pipefail

if [ "$(id -u)" != 0 ]; then
    echo "Run it with sudo:  sudo bash pi/setup.sh"
    exit 1
fi
USER_NAME="${SUDO_USER:-}"
if [ -z "$USER_NAME" ] || [ "$USER_NAME" = root ]; then
    echo "Run it with sudo from your normal account, not as root."
    exit 1
fi
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/ax4plotter
SERVICES="plotter-display plotter-vnc plotter-novnc plotter-upload"

echo "== Installing packages"
apt-get update
apt-get install -y xvfb openbox x11vnc novnc websockify x11-utils \
    x11-xserver-utils python3-tk python3-serial python3-flask \
    python3-gpiozero rsync

echo "== Turning off OctoPrint (it would hold the plotter's USB port)"
systemctl disable --now octoprint 2>/dev/null || true

echo "== Users"
id plotstudent >/dev/null 2>&1 || \
    useradd --system --no-create-home --shell /usr/sbin/nologin plotstudent
usermod -aG dialout "$USER_NAME"

echo "== Copying the program to $APP"
mkdir -p "$APP"
EXCLUDES=(--exclude .git --exclude uploads --exclude __pycache__
          --exclude .superpowers)
if [ -f "$APP/plotter_config.json" ]; then
    EXCLUDES+=(--exclude plotter_config.json)    # keep the Pi's settings
fi
rsync -a --delete "${EXCLUDES[@]}" "$SRC/" "$APP/"
mkdir -p "$APP/uploads"
python3 - "$APP/plotter_config.json" <<'EOF'
import json, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
except (OSError, ValueError):
    cfg = {}
cfg["run_as"] = "plotstudent"
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, sort_keys=True)
EOF
chown -R "$USER_NAME:$USER_NAME" "$APP"
chmod -R a+rX,go-w "$APP"
chmod 755 "$APP"/pi/*.sh

echo "== Letting the dashboard run student programs as plotstudent"
cat > /etc/sudoers.d/ax4plotter <<EOF
Defaults:$USER_NAME env_keep += "DISPLAY"
$USER_NAME ALL=(plotstudent) NOPASSWD: /usr/bin/python3
EOF
chmod 440 /etc/sudoers.d/ax4plotter
visudo -cf /etc/sudoers.d/ax4plotter

echo "== Services"
for s in $SERVICES; do
    sed "s#@USER@#$USER_NAME#g; s#@APP@#$APP#g" "$APP/pi/$s.service" \
        > "/etc/systemd/system/$s.service"
done
systemctl daemon-reload
systemctl enable $SERVICES
systemctl restart $SERVICES

IP="$(hostname -I | awk '{print $1}')"
echo
echo "Done."
echo "  Dashboard:    http://$IP:6080/vnc.html?autoconnect=1&resize=scale"
echo "  Upload page:  http://$IP:8000/"

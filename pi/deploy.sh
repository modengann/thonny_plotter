#!/bin/bash
# Send the committed code to the Pi and restart the plotter there.
# Run from Git Bash on the laptop, in the project folder:
#     bash pi/deploy.sh <user>@<pi-ip>       (first time)
#     bash pi/deploy.sh                      (after that; the Pi is remembered)
# Only committed work is sent.  The first run sets up ~/ax4plotter on the Pi;
# every run then runs pi/setup.sh there, which keeps the Pi's own
# plotter_config.json and the student uploads.
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-$(git config --get ax4.pi || true)}"
if [ -z "$TARGET" ]; then
    echo "Which Pi?  bash pi/deploy.sh <user>@<pi-ip>"
    exit 1
fi
git config ax4.pi "$TARGET"                      # remember it for next time
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "Note: uncommitted changes are NOT sent - commit them first if needed."
fi

echo "== Getting $TARGET ready to receive"
ssh -t "$TARGET" '
    command -v git >/dev/null || sudo apt-get install -y git
    [ -d ~/ax4plotter/.git ] || git init -q ~/ax4plotter
    git -C ~/ax4plotter config receive.denyCurrentBranch updateInstead'

echo "== Sending branch $BRANCH"
git push "$TARGET:ax4plotter" "$BRANCH"

echo "== Installing on the Pi"
ssh -t "$TARGET" "cd ~/ax4plotter && git checkout -q '$BRANCH' && sudo bash pi/setup.sh"

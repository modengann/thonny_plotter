# Running the AX4 plotter from a Raspberry Pi

The Pi sits next to the AX4 and does all the plotting.  Anyone on the school
network can watch and drive the dashboard from a browser, and students upload
their programs from a web page.  Plots keep going when every browser closes.

| What | Address |
|---|---|
| Dashboard | `http://<pi-ip>:6080/vnc.html?autoconnect=1&resize=scale` |
| Upload page (links to the dashboard) | `http://<pi-ip>:8000/` |

## What you need

- A Raspberry Pi 3B+ or newer running Raspberry Pi OS (Bookworm, Lite is fine).
  An old OctoPi card works if `cat /etc/os-release` says bookworm; if it says
  bullseye or older, re-flash with Raspberry Pi OS Lite (64-bit) using
  Raspberry Pi Imager, and turn on SSH in the Imager settings.
- The official Pi power supply.  A weak supply causes random USB drop-outs
  mid-plot.
- SSH access from the laptop (`ssh <user>@<pi-ip>`).

## First-time setup

The code goes to the Pi with git, over SSH.  Everything below runs in Git
Bash on the laptop, in the project folder.

1. **SSH key (once), so you aren't asked for the Pi's password every time:**

       ssh-keygen -t ed25519            (press Enter through the questions)
       cat ~/.ssh/id_ed25519.pub | ssh <user>@<pi-ip> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

2. **Commit the pen settings you want on the Pi.**  Only committed work is
   sent, and the Pi takes `plotter_config.json` from the first deploy.
   After that the Pi keeps its own copy.

3. **Deploy:**

       bash pi/deploy.sh <user>@<pi-ip>

   It sets up `~/ax4plotter` on the Pi (installing git if needed), pushes
   the current branch, then runs `pi/setup.sh` there.  Setup installs what
   it needs, turns OctoPrint off, copies the program to `/opt/ax4plotter`,
   and starts four services.  It asks for your password on the Pi once (for
   `sudo`) and prints the two addresses at the end.

4. Open the dashboard address in a browser.  You should see the dashboard.
5. Plug in the AX4 and go through the usual checklist: Connect, pen setup,
   origin.

**To update later:** commit, then `bash pi/deploy.sh` (the Pi's address is
remembered).  The Pi's own `plotter_config.json` (pen and calibration
settings) and the uploads are kept.  Deploying restarts the dashboard, so
set the origin again afterwards.

Don't edit files on the Pi itself: the next deploy refuses to update a
folder with local changes.  Make changes on the laptop and deploy.

## Things to know

- **Closing the dashboard window restarts it, and that resets the AX4.**
  The AX4 forgets its origin whenever its USB port is opened.  After a
  restart, set the origin again (the checklist won't let you plot until
  you do).  Don't close the dashboard window during a lesson.
- **Everyone shares one screen and one mouse.**  Agree who is driving.
- **Uploads** are checked before they are saved: only `turtle`, `math`,
  `random`, `time` and `colorsys` can be imported, and files, `eval`,
  `exec` and similar are refused.  Student programs run as the user
  `plotstudent`, who can't use the plotter or change any files, and are
  stopped after 20-25 seconds.
- Uploads collect in `/opt/ax4plotter/uploads/`.  Delete old ones by hand
  when the list gets long.
- The Open dialog is the plain Linux one.  It starts in the uploads folder.

## Physical STOP button (optional)

Wire a push button between **GPIO 17** (pin 11) and **ground** (pin 9).
Add this to `/opt/ax4plotter/plotter_config.json`:

    "stop_pin": 17,

then `sudo systemctl restart plotter-display` (and set the origin again).
Pressing it does exactly what the red STOP button does.  The AX4 power
switch is still the last resort.

## When something is wrong

| Problem | Try |
|---|---|
| Dashboard page won't load | `sudo systemctl status plotter-display plotter-vnc plotter-novnc` |
| Black screen in the browser | `sudo systemctl restart plotter-display plotter-vnc` |
| Upload page won't load | `sudo systemctl status plotter-upload` |
| "Couldn't run the program as user plotstudent" | Run `bash pi/deploy.sh` again |
| Connect says the plotter isn't found | Check the USB cable; `ls /dev/ttyUSB*` should list a port |
| Connect says the port is in use | `sudo systemctl disable --now octoprint` |
| See recent errors | `journalctl -u plotter-display -n 50` |

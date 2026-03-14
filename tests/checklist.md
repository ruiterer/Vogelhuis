# Birdcam — Manual Validation Checklist

Run these checks on the Raspberry Pi after installation.

## Pre-flight
- [ ] Raspberry Pi 4B with Pi OS Lite (Bookworm) installed
- [ ] Camera 3 NoIR connected and ribbon cable seated properly
- [ ] Pi connected to LAN via Ethernet or Wi-Fi
- [ ] SSH access working

## Installation
- [ ] `sudo bash install.sh` completes without errors
- [ ] `sudo bash tests/smoke_test.sh` — all tests pass

## Live Stream
- [ ] Open `http://<pi-ip>/` in Safari (iPhone/iPad/Mac)
- [ ] Open `http://<pi-ip>/` in Chrome (Mac/PC)
- [ ] Video stream loads and plays within 10 seconds
- [ ] Stream is stable for at least 5 minutes
- [ ] Clock/timestamp shown on the page (not in the video)
- [ ] Camera status badge shows "Live"
- [ ] Stream resolution info shown below video

## Snapshots
- [ ] Click "Snapshot" — success toast appears
- [ ] Snapshot file appears in "Recent Snapshots" section
- [ ] Click snapshot filename — JPEG downloads
- [ ] Downloaded image matches current stream resolution
- [ ] Filename format: `YYYY-MM-DD_HH-MM-SS_snapshot.jpg`
- [ ] Rapid clicking shows rate limit message (max 1 per 3 seconds)

## Fullscreen
- [ ] "Fullscreen" button works on desktop browser
- [ ] Video fills the screen in fullscreen mode

## Settings
- [ ] Open `http://<pi-ip>/settings`
- [ ] Change resolution from 720p to 480p, click Save
- [ ] "Restart Camera Stream" button works
- [ ] After restart, stream resumes at 480p
- [ ] Change title — reload page, new title appears in nav
- [ ] Change framerate — verify after stream restart
- [ ] Revert settings to original values

## Health
- [ ] Open `http://<pi-ip>/health`
- [ ] CPU percentage shown and updating every 5 seconds
- [ ] Memory usage shown with MB values
- [ ] CPU temperature shown (should be 40-70°C typical)
- [ ] Disk usage shown with GB values
- [ ] Uptime shown
- [ ] Camera status shows "online"
- [ ] All three services show "active"

## Multi-device
- [ ] Open stream on iPhone and iPad simultaneously
- [ ] Open stream on 3 devices at once — all play smoothly
- [ ] Stream remains stable during multi-viewer test

## Resilience
- [ ] `sudo systemctl stop birdcam-stream` — UI shows "Offline"
- [ ] `sudo systemctl start birdcam-stream` — stream resumes
- [ ] `sudo systemctl restart birdcam-stream` — stream recovers
- [ ] Unplug and replug camera ribbon cable — stream recovers after restart
- [ ] Reboot Pi (`sudo reboot`) — all services auto-start

## Hostname
- [ ] `http://<hostname>.local/` resolves and loads (e.g., `http://birdcam.local/`)

## Cleanup
- [ ] Create several test snapshots
- [ ] Verify cleanup runs: `sudo systemctl start birdcam-cleanup`
- [ ] Check logs: `cat /var/log/birdcam/cleanup.log`

## Update
- [ ] Modify a file, run `sudo bash update.sh`
- [ ] Services restart, config preserved
- [ ] UI shows updated content

## Edge Cases
- [ ] Disconnect Pi from network, reconnect — stream resumes
- [ ] Fill disk nearly full — cleanup removes oldest snapshots
- [ ] Set resolution to 1080p on Pi 4B — verify stability

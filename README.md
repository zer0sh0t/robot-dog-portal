# robot-dog-portal

Mission-control web portal for a Hiwonder PuppyPi (Raspberry Pi 5, ROS1 Noetic in Docker).
Single-file Python server (stdlib only) + a one-page web UI. Serves a live dashboard:
camera feed, telemetry (battery / online state), a thinking/command feed, and a big
**E-STOP** that publishes zero velocity to the robot.

## Files
- `server.py` - HTTP(S) server + robot bridge. No third-party deps (stdlib only).
- `index.html` - the whole UI (camera, telemetry cards, feed, E-STOP).
- `say.py` - optional Piper neural TTS (gives the portal a voice). Needs Piper + ffmpeg.
- `think.py` - append a line to the thinking feed.
- `portal_voice_watch.sh` - pipes browser mic/STT input into an operator session.
- `systemd/striker-portal.service` - run-on-host unit (HTTPS).

## Run it ON the robot (recommended for shared access)
Serves from the Pi itself, so teammates just join the robot's wifi and open the URL.

```bash
PUPPY_LOCAL=1 PUPPY_HOST=localhost PORTAL_BIND=0.0.0.0 PORTAL_PORT=8088 \
PUPPY_CAM_TOPIC=/usb_cam/image_raw python3 server.py
```
Then open `http://<robot-ip>:8088` (AP, LAN, or tailnet IP).

`PUPPY_LOCAL=1` makes the server run ROS commands locally via `docker exec` instead of
over SSH. Leave it unset to run the portal on a separate machine that reaches the robot
over SSH/Tailscale (set `PUPPY_HOST` to the robot IP).

## Env vars
| var | default | meaning |
|---|---|---|
| `PUPPY_LOCAL` | unset | `1` = run on the robot (local docker exec, no ssh) |
| `PUPPY_HOST` | `100.82.148.107` | robot IP (camera proxy + ssh target) |
| `PORTAL_BIND` | `100.69.20.22` | interface to bind (`0.0.0.0` for all) |
| `PORTAL_PORT` | `8088` | listen port |
| `PUPPY_CAM_TOPIC` | `/usb_cam_striker/image_raw` | ROS image topic to proxy |
| `PORTAL_CERT` / `PORTAL_KEY` | unset | PEM paths; if set, serves HTTPS |

## Security
Bind to a Tailscale IP (or the robot's private wifi) to keep it off the public internet.
E-STOP is always allowed. `runtime/` (certs, keys, logs, audio) is gitignored - never commit it.

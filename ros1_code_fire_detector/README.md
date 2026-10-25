# ROS1 robot dog: smoke + camera fire-candidate detection

Updated version: the physical flame sensor and temperature modes are removed.
The two inputs are now a smoke sensor and the robot's existing RGB camera.
Python 3 / ROS1 Noetic. Camera/LiDAR navigation nodes remain independent.

## Flow

1. Smoke GPIO node or an existing smoke driver publishes `/smoke_detected`.
2. Existing camera driver publishes `/camera/image_raw` (sensor_msgs/Image).
3. `camera_fire_detector.py` flags bright red/orange/yellow regions and publishes
   `/camera_fire_detected`. This is a color heuristic, NOT a trained fire model.
4. `fire_detector.py` combines smoke and camera readings for the dashboard.

| Topic | Type | Meaning |
|---|---|---|
| `/smoke_detected` | std_msgs/Bool | smoke/gas comparator threshold triggered |
| `/camera_fire_detected` | std_msgs/Bool | flame-colored region found in a new frame |
| `/camera/fire_debug` | sensor_msgs/Image | resized annotated image, on demand |
| `/fire_alert` | std_msgs/Bool | suspected hazard alarm |
| `/fire_sensor_fault` | std_msgs/Bool | required input missing, invalid, or stale |
| `/fire_status` | std_msgs/String | NORMAL, CHECKING, SMOKE_DETECTED, CAMERA_DETECTED, SMOKE_AND_CAMERA, ALARM_HELD, UNKNOWN, with fault details |

## Behavior

Either smoke OR a camera candidate sustained for 0.5 s triggers the alarm.
Each input has independent debounce. Both active gives SMOKE_AND_CAMERA.
Both inputs must remain fresh and safe for 3 s to clear an alarm.
Missing input for 2 s reports a fault and preserves any existing alarm.
Startup without readings is UNKNOWN: alert=false, fault=true. False alert alone
never means safe. State is in memory and resets to UNKNOWN after restart.

The camera uses HSV H=0..35, S>=120, V>=180 and a connected region covering at
least 1% of a 320x240 image. Tune min_area_ratio for your scene. Orange objects,
lamps, sunlight, and screens can cause false positives. Small, hidden, distant,
or differently colored flames can be missed. Camera images do not provide
measured temperature. This package does not visually detect smoke.
For more robust visual fire recognition, replace find_candidates with a trained,
validated model; none is included or downloaded here.

## Install and run

Extract ros1_fire_detector into ~/catkin_ws/src, then:

```bash
source /opt/ros/noetic/setup.bash
sudo apt-get install ros-noetic-cv-bridge python3-opencv
cd ~/catkin_ws
catkin_make
source devel/setup.bash
roslaunch ros1_fire_detector fire_detector.launch image_topic:=/camera/image_raw
```

Start the robot's existing camera driver separately. The launch file subscribes
to that driver's raw image topic; it does not open /dev/video0. Find the actual
topic with `rostopic list` and adjust image_topic. Compressed images require a
raw image publisher/republisher before this node. Only run one camera driver
owning the device. Camera publishers should provide fresh acquisition timestamps
using the same ROS clock as this node. Timestamped images older than 2 s or
more than 0.5 s ahead are rejected; zero stamps use receipt-time freshness only.

For a smoke module's digital output, enable the optional reader:

```bash
sudo apt-get install python3-rpi.gpio
roslaunch ros1_fire_detector fire_detector.launch gpio:=true smoke_pin:=27 image_topic:=/camera/image_raw
```

Smoke DO -> example BCM27 (physical pin 13); GND -> common ground.
Check that the robot kit does not already use this GPIO. The default is LOW on
detection; pass smoke_active_low:=false if your module is HIGH on detection.
Power the module per its datasheet. Raspberry Pi GPIO uses 3.3 V logic and is
not 5 V tolerant: level-shift a 5 V output before connection. Do not connect AO
(analog output) to GPIO: use an ADC/driver instead. A heater-equipped smoke
module may need a suitable separate supply with common ground, never GPIO power.
RPi.GPIO targets compatible Pi boards such as Pi 3/4; Pi 5 needs a compatible
backend/driver. The camera node uses ROS images and is independent of GPIO backend.

Smoke warmup/calibration must follow the manufacturer's instructions. An existing
smoke driver should withhold readings during warmup. Digital smoke output is a
comparator state, not calibrated ppm. The optional GPIO reader cannot distinguish
an unplugged wire that settles at a valid logic level. ROS topic freshness is
not electrical wire supervision. Do not run it alongside another smoke publisher.

## View dashboard outputs

```bash
rostopic echo /fire_status
rostopic echo /fire_alert
rostopic echo /fire_sensor_fault
rosrun rqt_image_view rqt_image_view /camera/fire_debug
```

Run each monitoring command in its own terminal. Keep fault/status visible on
the dashboard; monitor detector output heartbeats and mark it offline after 2 s
without a new message, since latched messages can outlive a stopped node.
Camera detection results are published only for processed new frames, so a
stopped camera or processing failures become an input timeout, not a safe result.

## Simulate without sensors/camera

Start fusion only:

```bash
roslaunch ros1_fire_detector fire_detector.launch camera:=false gpio:=false
```

In separate sourced terminals, publish both input streams:

```bash
rostopic pub -r 10 /smoke_detected std_msgs/Bool 'data: false'
```

```bash
rostopic pub -r 10 /camera_fire_detected std_msgs/Bool 'data: true'
```

Expect CAMERA_DETECTED and alert=true after about 0.5 s. Stop the camera test
publisher and restart with false; expect NORMAL after 3 s. Stop a publisher;
expect a sensor fault after 2 s. An existing alarm must remain set during fault.
Never run test publishers on the same topics as real sensor/detector publishers.

Offline fusion tests:

```bash
python3 -m unittest discover -s tests -v
```

## Changed files

- scripts/camera_fire_detector.py: NEW RGB image processing node.
- scripts/fire_detector.py: camera replaces flame/temperature input.
- scripts/gpio_sensors.py: smoke only; physical flame GPIO removed.
- launch/fire_detector.launch: image topic and camera node configuration.
- CMakeLists.txt, package.xml: camera dependencies and installation.
- tests/test_detector.py, tests/test_camera.py: decision and synthetic-image tests.

Experimental sensing prototype, not a certified life-safety fire alarm.
Test with simulated inputs and prerecorded images before hardware validation.

References:
- https://docs.opencv.org/4.x/da/d97/tutorial_threshold_inRange.html
- https://www.raspberrypi.com/documentation/computers/raspberry-pi.html

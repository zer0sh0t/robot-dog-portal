#!/usr/bin/env python3
"""ROS1 smoke + camera candidate fusion; hardware-independent logic."""
import threading
import time


class Detector:
    def __init__(self, timeout=2.0, confirm=0.5, clear=3.0):
        if timeout <= 0 or confirm < 0 or clear < 0:
            raise ValueError('Invalid timing parameters')
        self.timeout, self.confirm, self.clear = timeout, confirm, clear
        self.samples = {}
        self.since = {'smoke': None, 'camera': None}
        self.safe_since = None
        self.alert = False

    def update(self, name, hazard, now):
        old = self.samples.get(name)
        if hazard is None or not hazard:
            self.since[name] = None
        elif old is None or old[0] is not True or now - old[1] > self.timeout:
            self.since[name] = now
        self.samples[name] = (hazard, now)

    def evaluate(self, now):
        fresh = {k: k in self.samples and self.samples[k][0] is not None
                 and now - self.samples[k][1] <= self.timeout
                 for k in ('smoke', 'camera')}
        for k in fresh:
            if not fresh[k]:
                self.since[k] = None
        active = [k for k in fresh if fresh[k] and self.samples[k][0]]
        confirmed = [k for k in active if self.since[k] is not None
                     and now - self.since[k] >= self.confirm]
        fault = not all(fresh.values())
        if confirmed:
            self.alert = True
        if not fault and not active:
            if self.safe_since is None:
                self.safe_since = now
            if now - self.safe_since >= self.clear:
                self.alert = False
        else:
            self.safe_since = None
        if confirmed:
            state = 'SMOKE_AND_CAMERA' if len(confirmed) == 2 else confirmed[0].upper() + '_DETECTED'
        elif self.alert:
            state = 'ALARM_HELD'
        elif active:
            state = 'CHECKING'
        else:
            state = 'UNKNOWN' if fault else 'NORMAL'
        if fault:
            state += '; SENSOR_FAULT:' + ','.join(k for k in fresh if not fresh[k])
        return self.alert, fault, state


def main():
    import rospy
    from std_msgs.msg import Bool, String
    rospy.init_node('fire_detector')
    detector = Detector(float(rospy.get_param('~timeout', 2.0)),
                        float(rospy.get_param('~confirm_seconds', 0.5)),
                        float(rospy.get_param('~clear_seconds', 3.0)))
    lock = threading.Lock()

    def smoke_cb(msg):
        with lock:
            detector.update('smoke', msg.data, time.monotonic())

    def camera_cb(msg):
        with lock:
            detector.update('camera', msg.data, time.monotonic())

    alert_pub = rospy.Publisher('/fire_alert', Bool, queue_size=1, latch=True)
    fault_pub = rospy.Publisher('/fire_sensor_fault', Bool, queue_size=1, latch=True)
    status_pub = rospy.Publisher('/fire_status', String, queue_size=1, latch=True)
    subscribers = [rospy.Subscriber('/smoke_detected', Bool, smoke_cb, queue_size=1)]
    subscribers.append(rospy.Subscriber('/camera_fire_detected', Bool, camera_cb, queue_size=1))
    last_status = None
    # Wall-clock loop and monotonic freshness also work when /clock is paused.
    while not rospy.is_shutdown():
        with lock:
            alert, fault, status = detector.evaluate(time.monotonic())
        alert_pub.publish(Bool(data=alert))
        fault_pub.publish(Bool(data=fault))
        status_pub.publish(String(data=status))
        if status != last_status:
            rospy.logwarn(status) if alert or fault else rospy.loginfo(status)
            last_status = status
        time.sleep(0.1)


if __name__ == '__main__':
    main()

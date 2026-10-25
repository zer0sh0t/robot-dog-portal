#!/usr/bin/env python3
"""Runs inside the ROS1 environment; emits independent readings as JSON lines."""
import json
import math
import sys
import threading


def main():
    import rospy
    from sensor_msgs.msg import Temperature
    from std_msgs.msg import Bool, Float32

    config = json.loads(sys.argv[1])
    lock = threading.Lock()

    def publish(name, field):
        def callback(msg):
            value = getattr(msg, field)
            if isinstance(value, float) and not math.isfinite(value):
                return
            with lock:
                print(json.dumps({"sensor": name, "value": value}), flush=True)
        return callback

    rospy.init_node("portal_fire_sensors", anonymous=True, disable_signals=True)
    subscribers = []
    for name in ("smoke", "temperature", "fire_alert"):
        topic, message_type = config[name]
        cls = {"std_msgs/Float32": Float32, "sensor_msgs/Temperature": Temperature,
               "std_msgs/Bool": Bool}[message_type]
        field = "temperature" if message_type == "sensor_msgs/Temperature" else "data"
        subscribers.append(rospy.Subscriber(topic, cls, publish(name, field), queue_size=1))
    rospy.spin()


if __name__ == "__main__":
    main()

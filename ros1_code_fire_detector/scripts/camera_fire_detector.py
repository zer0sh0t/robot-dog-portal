#!/usr/bin/env python3
"""HSV color-based fire candidate detector, NOT a trained fire classifier."""
import cv2


def find_candidates(frame, min_area_ratio=0.01):
    """Return flame-colored regions occupying >= min_area_ratio of the frame."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 120, 180), (35, 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    min_area = frame.shape[0] * frame.shape[1] * min_area_ratio
    return [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= min_area]


def main():
    import rospy
    from cv_bridge import CvBridge, CvBridgeError
    from sensor_msgs.msg import Image
    from std_msgs.msg import Bool
    rospy.init_node('camera_fire_detector')
    topic = rospy.get_param('~image_topic', '/camera/image_raw')
    ratio = float(rospy.get_param('~min_area_ratio', 0.01))
    max_age = float(rospy.get_param('~max_image_age', 2.0))
    if not 0 < ratio <= 1 or max_age <= 0:
        raise ValueError('min_area_ratio must be in (0, 1]; max_image_age must be positive')
    bridge = CvBridge()
    detection_pub = rospy.Publisher('/camera_fire_detected', Bool, queue_size=1)
    debug_pub = rospy.Publisher('/camera/fire_debug', Image, queue_size=1)

    def callback(msg):
        # Reject queued old images when the driver supplies a timestamp.
        # Header stamps must share the ROS clock with this node.
        if msg.header.stamp != rospy.Time(0):
            age = (rospy.Time.now() - msg.header.stamp).to_sec()
            if age > max_age or age < -0.5:
                rospy.logwarn_throttle(5, 'Camera image timestamp is stale or ahead of ROS clock')
                return
        try:
            frame = bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            if frame.size == 0:
                raise ValueError('Empty camera image')
            frame = cv2.resize(frame, (320, 240))
            boxes = find_candidates(frame, ratio)
        except (CvBridgeError, cv2.error, ValueError) as error:
            # Do not publish false on invalid frames: fusion must report a fault.
            rospy.logwarn_throttle(5, 'Camera processing failed: %s' % error)
            return
        # Publish only for a newly processed image; never heartbeat cached results.
        detection_pub.publish(Bool(data=bool(boxes)))
        if debug_pub.get_num_connections():
            for x, y, w, h in boxes:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(frame, 'FIRE COLOR CANDIDATE' if boxes else 'NO COLOR CANDIDATE',
                        (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            debug = bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            debug.header = msg.header
            debug_pub.publish(debug)

    subscriber = rospy.Subscriber(topic, Image, callback, queue_size=1, buff_size=2**24)
    rospy.spin()


if __name__ == '__main__':
    main()


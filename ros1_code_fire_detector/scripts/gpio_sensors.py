#!/usr/bin/env python3
"""Optional digital-output smoke reader. Verify pin availability and voltage."""
import time
import rospy
import RPi.GPIO as GPIO
from std_msgs.msg import Bool


def main():
    rospy.init_node('smoke_gpio_sensor')
    pin = int(rospy.get_param('~smoke_pin', 27))
    active_low = bool(rospy.get_param('~smoke_active_low', True))
    GPIO.setmode(GPIO.BCM)
    try:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP if active_low else GPIO.PUD_DOWN)
        pub = rospy.Publisher('/smoke_detected', Bool, queue_size=1)
        while not rospy.is_shutdown():
            pub.publish(Bool(data=GPIO.input(pin) == (GPIO.LOW if active_low else GPIO.HIGH)))
            time.sleep(0.05)
    finally:
        GPIO.cleanup(pin)


if __name__ == '__main__':
    main()

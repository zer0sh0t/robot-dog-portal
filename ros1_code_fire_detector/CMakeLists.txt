cmake_minimum_required(VERSION 3.0.2)
project(ros1_fire_detector)
find_package(catkin REQUIRED COMPONENTS rospy std_msgs sensor_msgs cv_bridge)
catkin_package()
catkin_install_python(PROGRAMS scripts/fire_detector.py scripts/gpio_sensors.py scripts/camera_fire_detector.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(DIRECTORY launch DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})

# tello_driver
ROS driver wrapper for DJI/Ryze Tello drone

## Installation
* `$ cd <CATKIN_WS/SRC>`
* `$ git clone https://github.com/kei1107/tello_driver`
* `$ cd tello_driver/src/TelloPy`
* `$ sudo -H pip2 install -e .`
* `$ cd ../../`
* `$ chmod a+x cfg/Tello.cfg`
* `$ cd ../../`
* `$ catkin build tello_driver`

## Launch

* turn on drone and wait for its front lights to blink amber
* connect WiFi to drone's access point (e.g. `TELLO_######`)
* `$ roslaunch tello_driver launch/tello_node.launch`

# Node: 
[src/tello_driver_node.py](src/tello_driver_node.py)

Subscribe Topics:
* `~cmd_vel`: [geometry_msgs/Twist](http://docs.ros.org/api/geometry_msgs/html/msg/Twist.html)
* `~fast_mode`: [std_msgs/Empty](http://docs.ros.org/api/std_msgs/html/msg/Empty.html)
* `~image_raw`: [sensor_msgs/Image](http://docs.ros.org/api/sensor_msgs/html/msg/Image.html)
* `~takeoff`: [std_msgs/Empty](http://docs.ros.org/api/std_msgs/html/msg/Empty.html)
* `~throw_takeoff`: [std_msgs/Empty](http://docs.ros.org/api/std_msgs/html/msg/Empty.html)
* `~land`: [std_msgs/Empty](http://docs.ros.org/api/std_msgs/html/msg/Empty.html)
* `~palm_land`: [std_msgs/Empty](http://docs.ros.org/api/std_msgs/html/msg/Empty.html)
* `~flattrim`: [std_msgs/Empty](http://docs.ros.org/api/std_msgs/html/msg/Empty.html)
* `~flip`: [std_msgs/Uint8](http://docs.ros.org/api/std_msgs/html/msg/UInt8.html)

Publish Topics:
* `~image_raw` : [sensor_msgs/Image](http://docs.ros.org/api/sensor_msgs/html/msg/Image.html)
* `~odom` : [nav_msgs/Odometry](http://docs.ros.org/api/nav_msgs/html/msg/Odometry.html)
* `~imu` : [sensor_msgs/Imu](http://docs.ros.org/api/sensor_msgs/html/msg/Imu.html)
* `~status` : [tello_driver/TelloStatus](https://github.com/appie-17/tello_driver/blob/development/msg/TelloStatus.msg)

Parameters:
* `~tello_ip`
* `~tello_port`
* `~client_port`
* `~vid_port`
* `~conn_port`
* `~connect_timeout_sec`
* `~tello_name`

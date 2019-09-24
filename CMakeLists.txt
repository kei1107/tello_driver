cmake_minimum_required(VERSION 2.8.3)
project(tello_driver)
find_package(catkin REQUIRED COMPONENTS
        rospy

        cv_bridge
        image_transport
        #  h264_image_transport

        std_msgs
        nav_msgs
        sensor_msgs
        geometry_msgs

        dynamic_reconfigure
        message_generation

        tf
        )

add_message_files(
        FILES
        TelloStatus.msg
)

generate_messages(
        DEPENDENCIES
        geometry_msgs nav_msgs sensor_msgs std_msgs
)

generate_dynamic_reconfigure_options(
        cfg/Tello.cfg
)

catkin_package(
#        CATKIN_DEPENDS cv_bridge dynamic_reconfigure geometry_msgs h264_image_transport image_transport message_runtime nav_msgs rospy sensor_msgs std_msgs
)
include_directories(
        include
        ${catkin_INCLUDE_DIRS}
)

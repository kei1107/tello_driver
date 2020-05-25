#!/usr/bin/env python2
import rospy
from std_msgs.msg import Empty, UInt8, Bool
from std_msgs.msg import UInt8MultiArray
from sensor_msgs.msg import Image, CompressedImage, Imu
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from dynamic_reconfigure.server import Server
from tello_driver.msg import TelloStatus
from tello_driver.cfg import TelloConfig
from cv_bridge import CvBridge, CvBridgeError

import av
import math
import numpy as np
import threading
import time
from tellopy._internal import tello
from tellopy._internal import error
from tellopy._internal import protocol
from tellopy._internal import logger


class RospyLogger(logger.Logger):
    def __init__(self, header=''):
        super(RospyLogger, self).__init__(header)

    def error(self, s):
        if self.log_level < logger.LOG_ERROR:
            return
        rospy.logerr(s)

    def warn(self, s):
        if self.log_level < logger.LOG_WARN:
            return
        rospy.logwarn(s)

    def info(self, s):
        if self.log_level < logger.LOG_INFO:
            return
        rospy.loginfo(s)

    def debug(self, s):
        if self.log_level < logger.LOG_DEBUG:
            return
        rospy.logdebug(s)


def notify_cmd_success(cmd, success):
    if success:
        rospy.loginfo('%s command executed' % cmd)
    else:
        rospy.logwarn('%s command failed' % cmd)


class TelloNode(tello.Tello):
    def __init__(self):
        self.client_port = int(
            rospy.get_param('~client_port', 8890))
        self.vid_port = int(
            rospy.get_param('~vid_port', 6038))
        self.conn_port = int(
            rospy.get_param('~conn_port', 9617))
        self.tello_ip = rospy.get_param('~tello_ip', '192.168.10.1')
        self.tello_port = int(
            rospy.get_param('~tello_port', 8889))
        self.connect_timeout_sec = float(
            rospy.get_param('~connect_timeout_sec', 10.0))
        self.frame_id = rospy.get_param('~frame_id', 'tello')
        # self.stream_h264_video = bool(
        #     rospy.get_param('~stream_h264_video', False))
        self.bridge = CvBridge()
        self.frame_thread = None

        # Connect to drone
        log = RospyLogger('Tello')
        log.set_level(self.LOG_WARN)
        super(TelloNode, self).__init__(
            client_port=self.client_port,
            vid_port=self.vid_port,
            conn_port=self.conn_port,
            tello_ip=self.tello_ip,
            tello_port=self.tello_port,
            log=log)

        rospy.loginfo('Connecting to drone @ %s:%d' % self.tello_addr)
        self.connect()
        try:
            self.wait_for_connection(timeout=self.connect_timeout_sec)
        except error.TelloError as err:
            rospy.logerr(str(err))
            rospy.signal_shutdown(str(err))
            self.quit()
            return
        rospy.loginfo('Connected to drone')
        rospy.on_shutdown(self.cb_shutdown)

        # Setup dynamic reconfigure
        self.cfg = None
        self.srv_dyncfg = Server(TelloConfig, self.cb_dyncfg)

        # Setup topics and services
        # NOTE: ROS interface deliberately made to resemble bebop_autonomy
        self.pub_status = rospy.Publisher(
            'status', TelloStatus, queue_size=1, latch=True)

        self.pub_image_raw = rospy.Publisher(
            'image_raw', Image, queue_size=10)

        # if self.stream_h264_video:
        #     self.pub_image_h264 = rospy.Publisher(
        #         'image_raw/h264', H264Packet, queue_size=10)
        # else:
        #     self.pub_image_raw = rospy.Publisher(
        #         'image_raw', Image, queue_size=10)

        self.sub_takeoff = rospy.Subscriber('takeoff', Empty, self.cb_takeoff)
        self.sub_throw_takeoff = rospy.Subscriber('throw_takeoff', Empty, self.cb_throw_takeoff)
        self.sub_land = rospy.Subscriber('land', Empty, self.cb_land)
        self.sub_palm_land = rospy.Subscriber('palm_land', Empty, self.cb_palm_land)
        self.sub_flip = rospy.Subscriber('flip', UInt8, self.cb_flip)
        self.sub_cmd_vel = rospy.Subscriber('cmd_vel', Twist, self.cb_cmd_vel)

        self.subscribe(self.EVENT_FLIGHT_DATA, self.cb_status_log)

        self.frame_thread = threading.Thread(target=self.framegrabber_loop)
        self.frame_thread.start()

        # EVENT_LOG_DATA from 'TelloPy' package
        self.pub_odom = rospy.Publisher('odom', Odometry, queue_size=1, latch=True)
        self.pub_imu = rospy.Publisher('imu', Imu, queue_size=1, latch=True)
        self.subscribe(self.EVENT_LOG_DATA, self.cb_data_log)
        self.sub_zoom = rospy.Subscriber('video_mode', Empty, self.cb_video_mode, queue_size=1)

        rospy.loginfo('Tello driver node ready')

    def cb_video_mode(self, msg):
        if not self.zoom:
            self.set_video_mode(True)
        else:
            self.set_video_mode(False)

    def cb_dyncfg(self, config, level):
        update_all = False
        req_sps_pps = False
        if self.cfg is None:
            self.cfg = config
            update_all = True

        if update_all or self.cfg.fixed_video_rate != config.fixed_video_rate:
            self.set_video_encoder_rate(config.fixed_video_rate)
            req_sps_pps = True

        self.cfg = config
        return self.cfg

    def cb_status_log(self, event, sender, data, **args):
        speed_horizontal_mps = math.sqrt(data.north_speed * data.north_speed + data.east_speed * data.east_speed) / 10.0

        # TODO: verify outdoors: anecdotally, observed that:
        # data.east_speed points to South
        # data.north_speed points to East
        msg = TelloStatus(
            height_m=data.height / 10.,
            speed_northing_mps=-data.east_speed / 10.,
            speed_easting_mps=data.north_speed / 10.,
            speed_horizontal_mps=speed_horizontal_mps,
            speed_vertical_mps=-data.ground_speed / 10.,
            flight_time_sec=data.fly_time / 10.,
            imu_state=data.imu_state,
            pressure_state=data.pressure_state,
            down_visual_state=data.down_visual_state,
            power_state=data.power_state,
            battery_state=data.battery_state,
            gravity_state=data.gravity_state,
            wind_state=data.wind_state,
            imu_calibration_state=data.imu_calibration_state,
            battery_percentage=data.battery_percentage,
            drone_fly_time_left_sec=data.drone_fly_time_left / 10.,
            drone_battery_left_sec=data.drone_battery_left / 10.,
            is_flying=data.em_sky,
            is_on_ground=data.em_ground,
            is_em_open=data.em_open,
            is_drone_hover=data.drone_hover,
            is_outage_recording=data.outage_recording,
            is_battery_low=data.battery_low,
            is_battery_lower=data.battery_lower,
            is_factory_mode=data.factory_mode,
            fly_mode=data.fly_mode,
            throw_takeoff_timer_sec=data.throw_fly_timer / 10.,
            camera_state=data.camera_state,
            electrical_machinery_state=data.electrical_machinery_state,
            front_in=data.front_in,
            front_out=data.front_out,
            front_lsc=data.front_lsc,
            temperature_height_m=data.temperature_height / 10.,
            cmd_roll_ratio=self.right_x,
            cmd_pitch_ratio=self.right_y,
            cmd_yaw_ratio=self.left_x,
            cmd_vspeed_ratio=self.left_y,
            cmd_fast_mode=False,
        )
        self.pub_status.publish(msg)

    def cb_data_log(self, event, sender, data, **args):
        time_cb = rospy.Time.now()

        odom_msg = Odometry()
        odom_msg.child_frame_id = rospy.get_namespace() + '_base_link'
        odom_msg.header.stamp = time_cb
        odom_msg.header.frame_id = rospy.get_namespace() + '_local_origin'

        # Height from MVO received as negative distance to floor
        odom_msg.pose.pose.position.z = -data.mvo.pos_z  # self.height #-data.mvo.pos_z
        odom_msg.pose.pose.position.x = data.mvo.pos_x
        odom_msg.pose.pose.position.y = data.mvo.pos_y
        odom_msg.pose.pose.orientation.w = data.imu.q0
        odom_msg.pose.pose.orientation.x = data.imu.q1
        odom_msg.pose.pose.orientation.y = data.imu.q2
        odom_msg.pose.pose.orientation.z = data.imu.q3
        # Linear speeds from MVO received in dm/sec
        odom_msg.twist.twist.linear.x = data.mvo.vel_y / 10
        odom_msg.twist.twist.linear.y = data.mvo.vel_x / 10
        odom_msg.twist.twist.linear.z = -data.mvo.vel_z / 10
        odom_msg.twist.twist.angular.x = data.imu.gyro_x
        odom_msg.twist.twist.angular.y = data.imu.gyro_y
        odom_msg.twist.twist.angular.z = data.imu.gyro_z

        self.pub_odom.publish(odom_msg)

        imu_msg = Imu()
        imu_msg.header.stamp = time_cb
        imu_msg.header.frame_id = rospy.get_namespace() + '_base_link'

        imu_msg.orientation.w = data.imu.q0
        imu_msg.orientation.x = data.imu.q1
        imu_msg.orientation.y = data.imu.q2
        imu_msg.orientation.z = data.imu.q3
        imu_msg.angular_velocity.x = data.imu.gyro_x
        imu_msg.angular_velocity.y = data.imu.gyro_y
        imu_msg.angular_velocity.z = data.imu.gyro_z
        imu_msg.linear_acceleration.x = data.imu.acc_x
        imu_msg.linear_acceleration.y = data.imu.acc_y
        imu_msg.linear_acceleration.z = data.imu.acc_z

        self.pub_imu.publish(imu_msg)

    def cb_cmd_vel(self, msg):
        self.set_pitch(msg.linear.x)
        self.set_roll(-msg.linear.y)
        self.set_yaw(-msg.angular.z)
        self.set_throttle(msg.linear.z)

    def cb_shutdown(self):
        self.quit()
        if self.frame_thread is not None:
            self.frame_thread.join()

    def framegrabber_loop(self):
        # delay start
        rospy.sleep(2.0)

        try:
            container = None
            while self.state != self.STATE_QUIT:
                try:
                    container = av.open(self.get_video_stream())
                    break
                except BaseException as err:
                    rospy.logerr('fgrab: pyav stream failed - %s' % str(err))
                    rospy.loginfo('pyav restart')
                    rospy.sleep(0.5)
                    continue

            while self.state != self.STATE_QUIT:
                for frame in container.decode(video=0):

                    img = np.array(frame.to_image())
                    img_msg = None

                    try:
                        img_msg = self.bridge.cv2_to_imgmsg(img, 'rgb8')
                        img_msg.header.frame_id = self.frame_id
                    except CvBridgeError as err:
                        rospy.logerr('fgrab: cv bridge failed - %s' % str(err))
                        continue

                    # rospy.loginfo('publish img')
                    self.pub_image_raw.publish(img_msg)
                break
        except BaseException as err:
            rospy.logerr('fgrab: pyav decoder failed - %s' % str(err))

    def cb_takeoff(self, msg):
        success = self.takeoff()
        notify_cmd_success('Takeoff', success)

    def cb_throw_takeoff(self, msg):
        success = self.throw_and_go()
        if success:
            rospy.loginfo('Drone set to auto-takeoff when thrown')
        else:
            rospy.logwarn('ThrowTakeoff command failed')

    def cb_land(self, msg):
        success = self.land()
        notify_cmd_success('Land', success)

    def cb_palm_land(self, msg):
        success = self.palm_land()
        notify_cmd_success('PalmLand', success)

    def cb_flip(self, msg):
        if msg.data < 0 or msg.data > protocol.FlipForwardRight:
            rospy.logwarn('Invalid flip direction: %d' % msg.data)
            return

        success = None

        if msg.data is protocol.FlipFront:
            success = self.flip_forward()
        elif msg.data is protocol.FlipLeft:
            success = self.flip_left()
        elif msg.data is protocol.FlipBack:
            success = self.flip_back()
        elif msg.data is protocol.FlipRight:
            success = self.flip_right()
        elif msg.data is protocol.FlipForwardLeft:
            success = self.flip_forwardleft()
        elif msg.data is protocol.FlipBackLeft:
            success = self.flip_backleft()
        elif msg.data is protocol.FlipBackRight:
            success = self.flip_backright()
        elif msg.data is self.flip_forwardright():
            success = self.flip_forwardright()

        notify_cmd_success('Flip %d' % msg.data, success)


def main():
    rospy.init_node('tello_node')
    robot = TelloNode()
    if robot.state != robot.STATE_QUIT:
        rospy.spin()


if __name__ == '__main__':
    main()

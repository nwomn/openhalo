"""OpenHalo's bounded IMX219 mono input wrapper for Isaac ROS Argus.

The vendor launch file leaves the sensor mode at the Argus/GXF default.  This
wrapper makes the camera identity, sensor mode, and camera-info source explicit
so that a Camera Edge experiment can be reproduced without editing files under
``/opt/ros``.
"""

from pathlib import Path

import launch
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


_EXPERIMENT_DIR = Path(__file__).resolve().parent
_DEFAULT_CAMERA_INFO = f"file://{_EXPERIMENT_DIR / 'imx219_1280x720.yaml'}"


def generate_launch_description():
    camera_id = LaunchConfiguration("camera_id")
    module_id = LaunchConfiguration("module_id")
    mode = LaunchConfiguration("mode")
    camera_info_url = LaunchConfiguration("camera_info_url")

    launch_args = [
        DeclareLaunchArgument(
            "camera_id",
            default_value="0",
            description="Argus camera sensor id.",
        ),
        DeclareLaunchArgument(
            "module_id",
            default_value="0",
            description="Argus camera module id.",
        ),
        DeclareLaunchArgument(
            "mode",
            default_value="4",
            description="IMX219 sensor mode; mode 4 is 1280x720 at 60 FPS.",
        ),
        DeclareLaunchArgument(
            "framerate",
            default_value="60",
            description="GXF Argus capture rate for the selected sensor mode.",
        ),
        DeclareLaunchArgument(
            "camera_info_url",
            default_value=_DEFAULT_CAMERA_INFO,
            description="URL for the mode-matched camera info YAML.",
        ),
    ]

    argus_mono_node = ComposableNode(
        name="argus_mono",
        package="openhalo_isaac_ros_argus",
        plugin="openhalo::argus::OpenHaloArgusMonoNode",
        namespace="",
        parameters=[
            {
                "camera_id": camera_id,
                "module_id": module_id,
                "mode": mode,
                "framerate": LaunchConfiguration("framerate"),
                "camera_info_url": camera_info_url,
            }
        ],
    )

    argus_mono_container = ComposableNodeContainer(
        name="argus_mono_container",
        package="rclcpp_components",
        executable="component_container_mt",
        composable_node_descriptions=[argus_mono_node],
        namespace="",
        output="screen",
        arguments=["--ros-args", "--log-level", "info"],
    )

    return launch.LaunchDescription(launch_args + [argus_mono_container])

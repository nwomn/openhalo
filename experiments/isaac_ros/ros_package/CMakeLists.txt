cmake_minimum_required(VERSION 3.22.1)
project(openhalo_isaac_ros_argus LANGUAGES CXX)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()

ament_auto_add_library(openhalo_argus_mono_node SHARED
  src/openhalo_argus_mono_node.cpp
)
target_compile_features(openhalo_argus_mono_node PUBLIC cxx_std_17)

rclcpp_components_register_nodes(
  openhalo_argus_mono_node
  "openhalo::argus::OpenHaloArgusMonoNode"
)

set_target_properties(openhalo_argus_mono_node PROPERTIES
  BUILD_WITH_INSTALL_RPATH TRUE
  BUILD_RPATH_USE_ORIGIN TRUE
  INSTALL_RPATH_USE_LINK_PATH TRUE
)

ament_auto_package()

// OpenHalo's small configuration shim around the installed Isaac ROS Argus node.

#include <string>
#include <stdexcept>

#include "isaac_ros_argus_camera/argus_camera_mono_node.hpp"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_components/register_node_macro.hpp"

namespace openhalo
{
namespace argus
{

class OpenHaloArgusMonoNode : public nvidia::isaac_ros::argus::ArgusMonoNode
{
public:
  explicit OpenHaloArgusMonoNode(const rclcpp::NodeOptions & options)
  : nvidia::isaac_ros::argus::ArgusMonoNode(options)
  {
    framerate_ = declare_parameter<int>("framerate", 60);
    if (framerate_ <= 0) {
      throw std::invalid_argument("framerate must be greater than zero");
    }
  }

protected:
  void preLoadGraphCallback() override
  {
    // The released Argus node applies these values after the optimized graph
    // is exported; the framerate has no ROS parameter there, so apply all
    // camera controls through the same GXF override path before graph load.
    preLoadGraphSetParameter(
      "argus_camera", "nvidia::isaac::ArgusCamera", "camera_id",
      std::to_string(camera_id_));
    preLoadGraphSetParameter(
      "argus_camera", "nvidia::isaac::ArgusCamera", "module_id",
      std::to_string(module_id_));
    preLoadGraphSetParameter(
      "argus_camera", "nvidia::isaac::ArgusCamera", "mode",
      std::to_string(mode_));
    preLoadGraphSetParameter(
      "argus_camera", "nvidia::isaac::ArgusCamera", "fsync_type",
      std::to_string(fsync_type_));
    preLoadGraphSetParameter(
      "argus_camera", "nvidia::isaac::ArgusCamera", "framerate",
      std::to_string(framerate_));
  }

private:
  int framerate_{60};
};

}  // namespace argus
}  // namespace openhalo

RCLCPP_COMPONENTS_REGISTER_NODE(openhalo::argus::OpenHaloArgusMonoNode)

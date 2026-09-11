#!/usr/bin/env bash
set -eo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source /opt/ros/humble/setup.bash
overlay_setup="$script_dir/ros_package/install/setup.bash"
if [ -f "$overlay_setup" ]; then
  source "$overlay_setup"
fi
set -u
exec python3 "$script_dir/verify_60s.py" "$@"

# OpenHalo

[English](README.md)

OpenHalo 是一个以存在感治理为中心的个人 Agent Runtime，核心链路是：

`device -> context -> presence -> action`

它不是把聊天窗口当作产品中心，而是把设备当作边缘入口，把运行时当作长期存在的个人后端，并把 `Presence` 明确建模成一个可检查、可治理的决策层，用来决定系统该在什么时候、通过什么表面介入。

## 项目状态

这是一个 alpha 源码仓库，不是已托管的公网 Runtime。不要按这里的开发指令直接暴露携带 bearer credential 的 Runtime 端点；公网运行时仍需完成已跟踪的 TLS/WSS 和手机敏感屏幕采集治理工作。

## 这是什么

OpenHalo 目前是一个“架构驱动、但已经有可运行基线”的项目。仓库里已经具备：

- 长驻的 `Personal Runtime` 后端和 WebSocket Gateway
- 一个 host-class 的 `Device Edge`
- 一个常驻 terminal `Device Edge`
- 第一版 Android 手机 `Device Edge` 产品 UI
- 用于早期多边缘验证的跨边缘 action 路由
- 带 grounding 的 proposal formation、prompt/context inspection、以及 model-provider diagnostics

## 当前架构方向

- `Frontend / Device Edge`：驻留在设备侧，负责感知、交互、本地权限和低延迟动作
- `Backend / Personal Runtime`：跨设备长期存在，负责状态、Agent 行为、Presence 治理和动作编排

当前后端核心层次：

- `Gateway`
- `State / Context / Task`
- `Presence Router`
- `Agent Executor`
- `Action Layer`

## 部署场景

OpenHalo 正在面向几个清晰的部署场景建设：

- **标准个人部署**：一台公网或家庭服务器运行 `Personal Runtime + host edge`；一台电脑运行 desktop/terminal edge；一台 Android 手机运行 phone edge APK。
- **电脑托管部署**：一台个人电脑同时运行 `Personal Runtime + host edge + desktop/terminal edge`；Android 手机连接到这台电脑托管的 runtime。
- **未来环境型部署**：手机、电脑、智能家居、传感器和小型边缘 AI 节点一起组成低存在感的个人环境，让 OpenHalo 能理解生活上下文，并通过附近最不打扰的表面行动。

所有部署场景都保留同一条边界：

`Device Edge -> Edge API -> Gateway -> Personal Runtime`

服务器、电脑和手机可以物理上很近，甚至部分共址，但 edge 流量仍然应该穿过 Edge API 边界，而不是直接 import backend internals。

## 距离部署目标的进度

上面的部署场景需要三件事合到一起：稳定的 runtime、真实设备 edge、可安装的产品化打包。当前实现已经不再只是纯架构规划，但还没有到完整三端产品化交付。

| 部署要求 | 当前状态 | 还缺什么 |
| --- | --- | --- |
| Personal Runtime | 已有实现基线，包含 Gateway、state/context、proposal formation、Presence Router、action dispatch、grounding 和 diagnostics | 生产服务硬化和打包安装流程 |
| Server/host edge | 已实现 host-class edge，用于 runtime/host-device 验证和本地动作 | 一键服务器安装与服务监督 polish |
| Computer edge | 已完成常驻 terminal edge，支持前台用户输入和 runtime-delivered messages | 用户侧 desktop packaging 仍是后续工作 |
| Android phone edge | 已完成第一版产品 UI：`Connect`、`Global Chat`、`Settings`、隐藏诊断入口、preview APK，以及已验收的 M17.5 屏幕上下文观察基线 | 正式签名、分发体验、手机观察保活和敏感屏幕采集治理仍是后续工作 |
| 跨边缘交互 | 已实现公开 Edge API 的注册、观察、事件、动作、动作结果，以及经过 Presence 治理的路由 | 更广的真实设备场景和更丰富的 capability 覆盖 |
| 环境/家庭 edge 生态 | 长期方向：智能家居、传感器和小型边缘 AI 节点成为额外的 `Device Edge` 参与者 | 桥接集成、设备画像、安全策略和低存在感环境交互设计 |
| Mobile observation depth | `M17.5` 已验收：Android 可以上传被动的 `mobile.screen_context` / `mobile.screen_capture_health` evidence，并可通过 runtime context viewer 验证 | `M17.7` 负责观察保活/唤醒恢复；`M17.8` 负责 allowlist-first 的敏感屏幕采集治理 |
| Product packaging | 后续 `M21` | 可安装三端交付和 release-grade packaging |

完整路线图和里程碑状态见 [Project.md](Project.md)。

## Android 手机 Edge

第一版 Android 手机 Edge 产品 UI 已作为 `M17.4` 完成。它包含：

- `Connect`：默认连接/状态表面
- `Global Chat`：通过公开 Edge API 提交手机侧 `mobile.input`
- `Settings`：runtime URL、设备名、权限/后台控制、缓存/重置操作，以及隐藏开发诊断入口

预览 APK 通过 GitHub Releases 发布：

- [v0.17.4-mobile-edge-preview](https://github.com/nwomn/openhalo/releases/tag/v0.17.4-mobile-edge-preview)

这个 APK 是用于早期安装和测试的 debug-signed preview artifact。正式 release 签名、更新/分发体验和三端打包交付仍属于后续产品化工作。

## 快速开始

本地开发循环使用一个 `18765` 端口上的开发 runtime，加上本地 host/terminal edges，以及模拟器或手机 edge。

先使用仓库根目录虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

启动开发 runtime：

```bash
bin/run-runtime-dev
```

在第二个终端启动 host edge：

```bash
.venv/bin/python -m device_edge.host.host_daemon \
  --url ws://127.0.0.1:18765 \
  --token dev-token \
  --device-id host-edge-1
```

在第三个终端启动 terminal edge：

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon \
  --url ws://127.0.0.1:18765 \
  --token dev-token \
  --device-id terminal-edge-1
```

开发 helper 使用 `18765` 端口，让长期运行的服务器 runtime 可以保留
`8765`。服务器常驻启动方式见 [docs/runtime-deploy.md](docs/runtime-deploy.md)。

## 重要文档

- [Project.md](Project.md)：项目基线、路线图、架构方向、当前状态
- [docs/dev-env.md](docs/dev-env.md)：本地开发与验证流程
- [docs/runtime-deploy.md](docs/runtime-deploy.md)：开发与服务器常驻 runtime 启动方式
- [docs/android-edge-install.md](docs/android-edge-install.md)：Android 手机 Edge 设置和安装说明
- [docs/m17-android-edge-acceptance.md](docs/m17-android-edge-acceptance.md)：Android Edge 验证流程
- [docs/design/mobile-edge-ui/mobile-edge-ui-spec.md](docs/design/mobile-edge-ui/mobile-edge-ui-spec.md)：手机 Edge 产品 UI 设计基线
- [docs/ops/runtime-troubleshooting.md](docs/ops/runtime-troubleshooting.md)：生产 runtime 与 edge 连接排障
- [docs/plans/2026-06-16-runtime-architecture-design.md](docs/plans/2026-06-16-runtime-architecture-design.md)：架构基线设计
- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献与本地验证规则
- [SECURITY.md](SECURITY.md)：私密漏洞披露政策
- [LICENSE](LICENSE)：MIT 许可证

## 说明

- 真实 model-provider 链路目前还在持续硬化中。
- 第一版 Android 手机 Edge 产品 UI 已可用，但更完整的打包和分发体验仍在演进中。
- 源码协作已采用 MIT；仓库公开前仍须在 GitHub Security 设置中启用私密漏洞报告。
- 每当里程碑完成、接受或重新定界时，应同步更新 README 的实现进度表。
- 这个仓库还在快速演化，当前方向请始终以 `Project.md` 为准。

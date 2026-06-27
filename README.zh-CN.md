# OpenHalo

[English](README.md)

OpenHalo 是一个以存在感治理为中心的个人 Agent Runtime，核心链路是：

`device -> context -> presence -> action`

它不是把聊天窗口当作产品中心，而是把设备当作边缘入口，把运行时当作长期存在的个人后端，并把 `Presence` 明确建模成一个可检查、可治理的决策层，用来决定系统该在什么时候、通过什么表面介入。

## 这是什么

OpenHalo 目前是一个“架构驱动、但已经有可运行基线”的项目。仓库里已经具备：

- 长驻的 `Personal Runtime` 后端和 WebSocket Gateway
- 一个 host-class 的 `Device Edge`
- 一个常驻 terminal `Device Edge`
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

## 当前进展

这个项目已经不再只是纯架构规划。当前基线已经支持：

- 真实本地 runtime + edge 多进程验证
- 正式的 terminal-edge 交互表面
- 初步接入云模型的 proposal / reply 生成
- runtime grounding 与 memory 链路
- prompt/context 检查与 proposal 诊断

完整路线图和里程碑状态见 [Project.md](Project.md)。

## 快速开始

先使用仓库根目录虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

启动 runtime：

```bash
.venv/bin/python -m personal_runtime.main \
  --host 127.0.0.1 \
  --port 8765 \
  --token dev-token
```

在第二个终端启动 host edge：

```bash
.venv/bin/python -m device_edge.host.host_daemon \
  --url ws://127.0.0.1:8765 \
  --token dev-token \
  --device-id host-edge-1
```

在第三个终端启动 terminal edge：

```bash
.venv/bin/python -m device_edge.cli.terminal_daemon \
  --url ws://127.0.0.1:8765 \
  --token dev-token \
  --device-id terminal-edge-1
```

## 重要文档

- [Project.md](Project.md)：项目基线、路线图、架构方向、当前状态
- [docs/dev-env.md](docs/dev-env.md)：本地开发与验证流程
- [docs/plans/2026-06-16-runtime-architecture-design.md](docs/plans/2026-06-16-runtime-architecture-design.md)：架构基线设计

## 说明

- 真实 model-provider 链路目前还在持续硬化中。
- 路线图里，runtime-native credential / runtime-config 工作当前位于 `M16`。
- 这个仓库还在快速演化，当前方向请始终以 `Project.md` 为准。

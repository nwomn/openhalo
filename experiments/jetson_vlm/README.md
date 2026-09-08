# Jetson VLM 可视化消融示例

独立的 Camera Edge v2 实验程序，Python 3.10+，仅依赖设备已有的 OpenCV（含 GStreamer）与 Ollama。无需安装 OpenHalo Runtime，不连接 Gateway，不执行模型生成的动作。

## 运行

在 Jetson 上进入本目录：

```bash
python3 app.py --config presets/caption.json --host 0.0.0.0
# 停止上一个程序后切换：
python3 app.py --config presets/boxes.json --host 0.0.0.0
python3 app.py --config presets/grounded_subtitles.json --host 0.0.0.0
```

浏览器打开 `http://192.168.0.30:8765`。Jetson 本机也可打开 `http://127.0.0.1:8765`。
默认仅监听回环；显式 `--host 0.0.0.0` 是将摄像头预览开放给可信局域网，无登录功能。
Ctrl+C 退出；界面可暂停后续分析（正在进行的请求会完成），视频仍继续。`--paused` 启动时只预览。

## 实验因素

| 配置 | task | display | 用途 |
| --- | --- | --- | --- |
| caption.json | caption | subtitles | 只生成描述 |
| boxes.json | grounded | boxes | 描述加坐标，画框 |
| grounded_subtitles.json | grounded | subtitles | 同样生成坐标，但只显示字幕 |

caption 对比 grounded 改变模型任务、输出长度与输入 prompt；不能将耗时差全部归因于绘图。
两个 grounded 配置对同一图片产生完全相同的 API 请求，区别只在前端渲染。
界面渲染在浏览器内；采集 FPS 是 Jetson capture FPS，不是假称浏览器实际展示 FPS。
当前不采集浏览器绘制耗时，不能用模型请求耗时证明绘图开销。

统一固定模型、输入宽度、context、seed、temperature、max_tokens，在 JSON 内调整（字段见 config.py）。
公平比较优先使用**同一固定图片**，而不是内容持续变化的直播：

```bash
python3 app.py --config presets/caption.json --source /absolute/path/frame.jpg --requests 6
python3 app.py --config presets/boxes.json --source /absolute/path/frame.jpg --requests 6
python3 summarize.py runs/<run-id>
```

每次启动有独立运行目录，保存配置、prompt/schema 和 requests.jsonl。
配置快照同时记录 Ollama 版本、本地模型 digest 和启动时加载状态。
每次请求记录输入 JPEG SHA256、尺寸、采样时间、首个内容片段延迟、请求耗时、加载/输入处理/生成耗时、token 数、完整模型输出与格式错误。
首个片段常是 JSON 标点，并非第一条有效语义。主要判断可用延迟为 frame_to_result_s。
默认汇总排除首次请求；首轮未必真是冷启动，检查 load_s，交替 A/B 顺序并使用足够样本。
模型持有时间为 5 分钟，不将不同残留模型并行加载作为比较条件。
重复完全相同的图片可能命中视觉/prompt缓存；必须同时报告 prompt_eval_s，不能把缓存命中后的耗时当作实时新画面速度。
不默认保存视频、图片，只保存模型描述与指标；网页中的判读帧保存在进程内存。

## 架构

- `camera.py`：唯一采集线程，保存最新帧；GStreamer appsink 容量 1，丢弃过期帧。
- `model.py`：任务 prompt、JSON schema、Ollama 流协议和结果校验，与 UI 无关。
- `app.py`：单个推理工作线程、JSONL 记录、标准库 HTTP 服务组合。
- `index.html`：最新 JPEG 预览 + SVG/中文字幕；旁边显示模型实际判读的采样帧。浏览器至多一帧请求在途，以约30 FPS为上限，不累积网络请求；另保留 MJPEG 接口供外部工具使用。
- `config.py`：启动配置；`summarize.py`：实验汇总。

采集不会等待推理；模型结束后取最新帧，不积累任务队列。没有重试、自动改模型、自动修改坐标等回退逻辑。失败显式显示并暂停分析。
框在当前预览上的位置来自历史采样帧；不提供虚假的目标跟踪。显示真实采样年龄，完成后 overlay_ttl 秒隐藏，旁边保留对应原帧供核对。未来跟踪可作为独立实验因素。
本示例不接受生产性能、4K 摄像头、长期散热或 Runtime 端到端链路。

## 测试

```bash
python3 -m unittest -v test_model.py
```

覆盖显示变量不会改变模型请求、定位任务合同、非法坐标和不完整流。

# MobileVLM V2：物品 unknown 后的 ROI 回退验证

2026-09-12。用户明确了条件回退意图：低层物品识别不确定时，把 ROI 交给 MobileVLM V2 作具体识别。本轮完成这条路线的**缓存观测路由＋ROI 语义回放实验**，不等于生产管线或完整 Camera Edge 验收。

结果：中性提示下，两张手机正／背面 ROI 都输出手机；四张空手 ROI 没有继续声称手里有创可贴等物品，但未提供可直接消费的明确 empty-hand 标签。两张螺丝刀仍被误认成铅笔／红笔。另有三个高分错误因未触发回退而原样保留。具体组合有局部补充价值，尚未通过可靠物品识别验收。

用户在本轮结果后明确判断“这个组合还是有价值的”，因此保留为继续验证的组合候选。该判断不改变螺丝刀、高分误判、空手标签、连续调度和实时延迟尚未解决的状态，也不代表已经接受为完整 Camera Edge 实现。

## 本轮路由定义

1. 复用上一轮实际保存的手部区域与 YOLO26n-cls 原始 top-1；不是手势 unknown。
2. 物品分类分数 `<0.7` 时触发 MobileVLM ROI。没有手部候选时没有可用 ROI，不自动改用陈旧区域。
3. 分数 `>=0.7` 保留分类器结果，不调用 MobileVLM。
4. 使用自动手部区域（上一轮扩大2.2倍），不是人工物品真值框。每个常规窗口取时间中点附近帧，再取最大手部框。
5. MobileVLM 只接收图像和同一提示，不接收分类器猜出的名称、真值、窗口名称或测量 JSON。

**这次单独验证分类器分数门控。** 整图检测器与分类器的冲突仲裁、是否已经确定抓握、手势类型、跟踪质量与新目标触发都没有加入门控。因此，原先整图检测器能正确检测的手机正面，也可能因 ROI 分类器不确定而触发。本轮不能冒充完整多专家决策器。

## 输入、对照与运行条件

- 复用 `/home/jetson/openhalo-specialist-expanded/fresh-2157/capture.mp4`；当前视频哈希与上一轮记录相同。
- 8个常规样本来自上一轮预先标好的窗口：手机正面、螺丝刀A、握拳、点赞、V、手机背面、螺丝刀B、空手张掌。全部触发回退。
- 额外选取手机正面／螺丝刀A／螺丝刀B各一个最高分类分数样本，专门检查高分误判绕过回退。这三个是有意选择的压力样本，不能与8个窗口中点样本合成总体准确率。
- 每个触发样本做 ROI 与同源整图配对，各重复2次。整图是反事实诊断，实际回退分支使用 ROI。
- 两套提示分别运行，总共64次正式生成（每套8样本×2画面×2重复），每套另有一次预热。三个未触发样本没有调用 VLM。重复结果一致，不计作独立正确率样本。
- 使用原已验证 MobileVLM V2 1.7B 权重／运行时，语言主干 NF4、视觉／projector／输出头 FP16，168个4bit线性层，加载无缺失或额外权重键。48 token上限、贪心生成。
- MediaPipe手势模型、TensorRT检测与分类模型同时驻留，并用黑图分配实际上下文；真实门控使用缓存观测，没有同步重新运行专家或实时采集。

## 提示对照

P1 是定向物品问答：

> What object, if any, is physically held by the visible hand? Reply with only the object name, 'empty hand', or 'unclear'. Do not name background objects. If the visual evidence is insufficient, reply 'unclear'.

P1 在明显手机和多张空手图上反复输出 `The visible hand is holding an empty hand.`，第一张螺丝刀 ROI 也给出类似无意义措辞。第二张螺丝刀 ROI 被称为 red pen。该提示失败；这些原始输出全部保留。

随后只改提示为 P2：

> Describe this image briefly.

保持相同样本、门槛、ROI、模型和生成配置。这是开发集上的提示消融，不是新的独立验收。

## 中性提示 P2 的实际输出

| 样本 | ROI 回答 | 同帧整图对照／判断 |
| --- | --- | --- |
| 手机正面 | A person holding a cell phone in their hands. | 整图也识别手机；ROI 没有额外描述背景投影设备 |
| 手机背面 | A man holding a cell phone with a picture on it. | 整图也识别手机；有别于上一轮检测器背面漏检和分类器错误 top-1 |
| 螺丝刀A | A man holding a pencil in his hands. | 整图也误认为铅笔 |
| 螺丝刀B | A man holding a red pen in his hand. | 整图误认为铅笔 |
| 空手握拳 | A person with their hands up in a picture. | 未明确说空手，手势描述粗糙；整图长答出现无依据心理活动描述并达到token上限 |
| 点赞 | A man giving a thumbs up in front of a computer screen. | 手势正确，无虚构手持物品；仍额外推断背景为computer screen |
| V | A man in a white shirt is making a peace sign. | 与可见手势相容，不表示知道动作意图 |
| 空手张掌 | A man holding his hand up in front of a computer screen. | 无虚构手持物品，但没有明确empty-hand输出；整图描述错手势、加入心理状态并达到token上限 |

不能把“没有提及物品”自动转成“确认空手”。本轮输出是原始描述，未添加让它变成可靠结构化物品标签的解析器。ROI 比整图减少了这几个样本中的部分冗长／无依据描述，但螺丝刀识别没有改善。

## unknown-only 门控的漏洞与调用量

三个高分压力样本分别保留：

| 实际物品 | 分类器错误标签／分数 | 实际路由 |
| --- | --- | --- |
| 手机 | iPod / 0.81445 | 不触发 VLM，保留错误 |
| 螺丝刀A | bow / 0.75017 | 不触发 VLM，保留错误 |
| 螺丝刀B | syringe / 0.77819 | 不触发 VLM，保留错误 |

所以 `unknown → VLM` 能纠正部分低分错误，高分错误仍需要另行验证的冲突检查、新目标验证或周期复核等机制，不能声称门槛本身足够。

在完整原录像416个采样帧中，有手149帧；其中146帧至少有一个 ROI 分类分数低于0.7。共162个手部 ROI 中158个会触发。如果逐采样帧排队调用，低层模型几乎每次看到手都会请求 VLM。这与“偶尔补充”不同。

连续管线仍需实现并验证：同一目标请求合并、进行中任务去重、只保留最新待处理ROI、结果时间戳／失效条件、目标消失清理与新目标不复用旧结果。本轮均未实现；没有后台摄像头服务或 Runtime 消费者。

## 耗时与资源

| 测量 | P1 定向提示 | P2 中性提示 |
| --- | --- | --- |
| ROI 16次正式回答 最小／中位／最大 | 1.568 / 1.580 / 1.934秒 | 1.627 / 1.869 / 2.147秒 |
| 整图16次回答 最小／中位／最大 | 1.597 / 1.609 / 1.893秒 | 1.781 / 2.048 / 6.418秒 |
| RAM 峰值 | 6579 MB | 6515 MB |
| 整机 swap 采样范围 | 805–885 MB | 885–909 MB |

从保存PNG读取、预处理、提示编码到解码文本计时；排除模型加载和首次预热。专家模型驻留但真实专家测量、ROI提取和路由结果来自缓存；计时不含这些步骤、CSI采集、排队、传输与Runtime。不能把此前专家耗时直接相加后宣称实时P95。swap读数增加，尚未证明无swap依赖或长期稳定。

P2整图的两个空手样本每次都达到48 token上限；不是完整答案。P2全部ROI回答没有截断。两个提示的差别说明“回退模型可加载”与“回退能给可靠结果”仍是不同验收项。

## 状态、证据与复现

该实验将第二条路线细化为条件触发的ROI语义补充，已经开始并完成一轮有限回放；不是此前测量JSON拼接的重复实验。第一条无VLM实验的历史结果保持。完整Camera Edge、五秒实时事件标签目标、身份与Runtime边界均不变。

- [固定样本／路由／ROI像素框与哈希](evidence/2026-09-12-roi-fallback/cases.json)
- [P1完整原始输出](evidence/2026-09-12-roi-fallback/prompt-v1.json)、[P1源代码快照](evidence/2026-09-12-roi-fallback/roi_fallback_v1.py)
- [P2完整原始输出](evidence/2026-09-12-roi-fallback/prompt-neutral.json)
- [P1资源日志](evidence/2026-09-12-roi-fallback/prompt-v1-tegrastats.log)、[P2资源日志](evidence/2026-09-12-roi-fallback/prompt-neutral-tegrastats.log)
- [ROI准备脚本](../../experiments/specialist_temporal/prepare_roi_fallback.py)、[回退／对照脚本](../../experiments/specialist_temporal/roi_fallback.py)

图片留在 Jetson `/home/jetson/openhalo-roi-fallback/media/`，不纳入Git。运行没有安装包或修改现有模型环境；实验进程已退出。两份报告完成状态、对应脚本哈希、是否触发与实际生成调用一致性、重复输出一致性均已核对。

```sh
/home/jetson/openhalo-mobilevlm-v2-venv/bin/python \
  /home/jetson/openhalo-roi-fallback/scripts/roi_fallback.py \
  --output /home/jetson/openhalo-roi-fallback/run-NEW \
  --prompt 'Describe this image briefly.'
```

输出目录必须不存在。模型上下文预热仍会执行；真实样本路由沿用已保存的 cases.json。

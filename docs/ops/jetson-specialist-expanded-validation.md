# Camera Edge 专用分类模型扩展验证

日期：2026-09-12。**本轮完成：训练好的手势分类获得有限有效结果；所测手中物品识别组合不满足需求。完整多专家路线仍未充分验证，也未通过 Camera Edge 验收。**

## 实际增加的能力

| 组件 | 输入／输出 | 本轮新增内容 |
| --- | --- | --- |
| MediaPipe Gesture Recognizer v1 | 手部关键点到预训练手势类别 | 新增学习到的手势 embedding／分类器；不再仅靠手指距离规则定义静态手势 |
| YOLO26n TensorRT 检测 | 整图到 80 类物品框 | 复用已有检测模型，独立评估手机及手部框重叠；不是新的检测权重 |
| YOLO26n-cls TensorRT 分类 | 扩大的手部区域到 ImageNet 1000 类 top-5 | 新接入独立物品分类模型，检验能否补充检测器不支持的螺丝刀类别 |
| 短时状态保持 | 手势类别／分数到稳定类别事件 | 预先固定分数 ≥0.7、持续 ≥0.4 秒；保留过滤前原始类别 |

人脸身份识别没有实现；本轮也没有新增人脸朝向、匿名跟踪或身份替代组件。没有 VLM/LLM、吃东西／意图解释、抓握接触模型或 Runtime 接入。

手势模型包括掌部检测、手部关键点、手势 embedding 与分类网络；其预设静态类别包含张掌、握拳、点赞、V 等，输出类别并不表示同意、胜利或打招呼等意图。参考：[官方模型说明](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/index)、[Python API 使用说明](https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/python)。

模型从官方版本 `float16/1/gesture_recognizer.task` 下载，8,373,440 字节，SHA-256 `97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482`。使用现有 MediaPipe 0.10.18、Ultralytics 8.4.24、TensorRT 环境；没有安装依赖或更改 NVIDIA PyTorch。两个 YOLO engine 的完整哈希包含在运行证据中。

## 验证过程与真值边界

- 旧空手挥动片段：24 个采样帧，14 帧检出手。旧吃东西片段：28 个采样帧，7 帧检出手。
- 首次新录像约90秒：主要是低头、转头和交谈，没有清晰完成计划中的正例展示。保留为自然场景控制，不把动作提示当作已发生真值。416 帧没有稳定目标手势输出。文件中的原始 case 名称仍为计划名，不代表真值。
- 用户再次确认后录制第二段约90秒：包含手机正面、螺丝刀、手势、手机背面、再次螺丝刀和空手展示。
- 第二段使用相同源代码、模型、阈值与裁剪规则；先按每秒联系图选择保守可见区间，再读取预测，结果保存到 reference-windows.json。没有按预测挑选成功帧或事后调阈值。
- 这是同一人、同一场景的一次短录制；没有独立逐帧精标，不构成总体准确率、动作起落真值或五秒实时 P95 验收。

## 手势分类结果

以下分母为人工可见稳定区间内的采样帧；“模型正确”表示该帧至少一只候选手的原始 top-1 是目标类别。“门控后”还要求单只手、分数门槛及持续时间，可能保持上一状态或弃答。

| 手势／时间窗 | 模型正确类别 | 单帧门控后正确 | 稳定状态正确 |
| --- | --- | --- | --- |
| 握拳，29–31.2秒 | 11/11 | 10/11 | 9/11 |
| 点赞，32–33.4秒 | 7/7 | 5/7 | 4/7 |
| V，34–35.4秒 | 6/6 | 5/6 | 6/6 |
| 最后张掌，51–53秒 | 9/9 | 0/9 | 0/9 |

最后张掌的原始分数为 **0.672–0.699**，因此被固定 0.7 门槛全部挡掉。这是模型输出与门控的具体差异，不能归结为模型完全不识别张掌。另一次较早张掌在20.565秒产生稳定 Open_Palm 事件，因此四个静态类别都曾形成事件，但张掌的重复表现不稳定。

新片段事件依次包含：20.565秒 Open_Palm，29.440秒 Closed_Fist，32.687秒 Thumb_Up，34.203秒 Victory；其余转入 unknown 的事件与原始观测一并保存。该顺序是固定静态类别的时间记录，不是模型理解了举起、放下或动作意图。

全片416帧，149帧检出手；稳定状态为 unknown 385、Open_Palm 4、Closed_Fist 10、Thumb_Up 7、Victory 10。手势阈值需要独立样本校准，不能仅降低到恰好通过本段。

## 手中物品结果

| 场景／时间窗 | 整图检测器 | 手部区域分类器 |
| --- | --- | --- |
| 手机正面，3–5.5秒 | 12/12帧检出 cell phone | 23个候选手区域，手机类别 top-1 为0；常见 iPod 等错误类别 |
| 手机背面，39–40.5秒 | 0/7帧检出手机 | 7个手区域 top-1 均错误；手机在其中4个区域的 top-5 里 |
| 螺丝刀两次，10–14.5及44–48.5秒 | 类别表没有螺丝刀；出现8次 toothbrush 错误框 | 共40个手区域，螺丝刀 top-1 为0，top-5 仅1；主要输出 syringe／bow |
| 空手张掌，51–53秒 | 偶发非目标物品框 | 9/9个区域 top-1 都是 Band_Aid |
| 空手握拳，29–31.2秒 | 出现4次 donut 框 | 11/11个区域 top-1 都是 Band_Aid |

23个手机正面手区域来自12帧中的重复／多手候选，不是23个独立正例。所有错误类别原样保留，没有因为不合理而删除。

手部区域以关键点边界中心为中心，按最大边长扩大2.2倍后做分类；区域容易包含手、脸和背景。模型是封闭类别的 ImageNet 分类器，没有 empty-hand 类或可靠的分布外拒绝能力。top-1/top-5 只是类别排名，不能自动变成“持有物品”。

二维重叠也会包含背景电视；本轮结果只标为 `2d_hand_box_overlap; holding_unverified`。**手机正面被识别，只能证明图中存在手机，尚未验证抓握关系。** 螺丝刀不在检测器类别里，这是类别覆盖缺口；分类器虽然有该类别，所测表现依然失败。

## 定位问题还是分类问题

增加4张人工裁剪诊断图：手机正面4秒、背面39.5秒、螺丝刀45.5秒、空手52秒。坐标先人工选择；分别测试默认中心裁剪和正方形填充保全物体。这是人工 ROI 诊断，不计入自动检测准确率。

- 手机正面两种裁剪都没正确输出手机 top-1。
- 手机背面填充后手机升至第2名（约0.099），top-1 仍为 iPod。
- 螺丝刀两种裁剪都未进入 top-5。
- 空手仍输出 Band_Aid。

再用同目录原始 `yolo26n-cls.pt` 与 TensorRT engine 对这4张默认裁剪作对照：**4/4 top-1 一致、类别映射一致，最大概率绝对差低于0.0018。** 这支持错误主要不是这些样本上的 TensorRT 转换导致的；不代表完成全部数值／精度验收。原始 PyTorch checkpoint 的哈希也已记录。

## 性能、验收与范围

第二段记录按名义5Hz采样，实际相邻采样约0.216秒。CPU 手势模型与 GPU 检测／分类模型驻留，逐帧串行处理。

| 指标 | 本次结果 |
| --- | --- |
| 每采样帧模型总处理均值／P95 | 141.36 / 209.77 ms |
| 手势均值 | 101.43 ms |
| 检测均值 | 31.47 ms |
| 按全部采样帧平均的 ROI 分类／整理 | 8.46 ms；无手帧跳过分类，不能当作每个 ROI 耗时 |
| 全片最大模型处理耗时 | 435.21 ms |
| 整机 RAM 范围 | 3206–4206 MB |
| 已有 swap | 808 MB，采样读数不增加 |
| GPU 采样占用范围 | 0–99%；500ms采样，不代表持续满载 |
| CPU 温度 | 53.2–55.4°C |

统计只排除每片第一帧，不排除分类器在第一次有手帧上的延迟加载。计时不含全部视频读取／解码、CSI采集、编码、队列、传输和 Runtime；没有建立端到端事件 P95≤5秒。不同于上一轮，身体与面部模型未同时运行，因此不能用两轮时间差声称增加模型却加速。

结论分项：

- **完成有限验证：**静态手势分类提供了原先几何规则没有的类别输出；手机正面目标检测可用。
- **本组合未通过：**自动手中物品类别识别、空手拒绝、手机背面与螺丝刀识别。
- **仍需验收：**手势门控校准、多人关联、动作开始／结束、真实抓握关系、连续运行和实时延迟。
- **未实现：**人脸身份识别；本轮没有新增身份、朝向或匿名跟踪组件。
- **范围结论：**具体组件结果不能代表全部多专家路线已经失败或成功。完整路线仍未充分验证，Runtime 与 Camera Edge 验收保持不变。

## 证据与复现

- [源代码](../../experiments/specialist_temporal/expanded.py)、[人工裁剪诊断](../../experiments/specialist_temporal/crop_diagnostic.py)
- [冻结配置与报告协议](evidence/2026-09-12-specialist-expanded/protocol.json)
- [全部控制片段原始结果](evidence/2026-09-12-specialist-expanded/control-run.json)
- [第二段逐帧原始结果与模型／视频哈希](evidence/2026-09-12-specialist-expanded/fresh-run.json)
- [人工窗口](evidence/2026-09-12-specialist-expanded/reference-windows.json)、[分窗统计](evidence/2026-09-12-specialist-expanded/assessment.json)
- [裁剪诊断](evidence/2026-09-12-specialist-expanded/crop-diagnostic.json)、[PyTorch 对照](evidence/2026-09-12-specialist-expanded/classifier-parity.json)
- [资源日志](evidence/2026-09-12-specialist-expanded/tegrastats.log)

原始视频和诊断图留在 Jetson `/home/jetson/openhalo-specialist-expanded/fresh-2153/` 与 `fresh-2157/`，不纳入 Git。脚本位于其 `scripts/`，新下载模型只放在其 `models/`。

```sh
python3 /home/jetson/openhalo-specialist-expanded/scripts/expanded.py \
  --cases /home/jetson/openhalo-specialist-expanded/cases-fresh-v1.json \
  --output /home/jetson/openhalo-specialist-expanded/replay-NEW --hz 5
python3 /home/jetson/openhalo-specialist-expanded/scripts/crop_diagnostic.py
```

第一条命令输出目录必须不存在。第二条仅用于人工裁剪诊断，会重写该实验目录中的 `crop-diagnostic.json`。

# Actual complete model conversation prompts

These are the actual strings passed through image-token tokenization, including the official conversation template.
The <image> marker is replaced by image embeddings during inference. Identical repeated prompts are shown once; repeat indices are listed.

## challenge-food

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"person","confidence":0.8822,"bbox":[0.1278,0.2231,0.7103,0.994]},{"id":"d1","label":"tv","confidence":0.3759,"bbox":[0.0002,0.0033,0.2983,0.4898]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.6049,"y":0.5289,"confidence":0.9992,"usable":true},"left_shoulder":{"x":0.5914,"y":0.708,"confidence":0.9908,"usable":true},"right_shoulder":{"x":0.2348,"y":0.8154,"confidence":0.978,"usable":true},"left_elbow":{"x":0.654,"y":0.9416,"confidence":0.4744,"usable":false},"right_elbow":{"x":0.1815,"y":1.0,"confidence":0.0021,"usable":false},"left_wrist":{"x":0.7464,"y":0.9714,"confidence":0.1927,"usable":false},"right_wrist":{"x":0.4242,"y":0.922,"confidence":0.019,"usable":false}}}]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"person","confidence":0.8822,"bbox":[0.1278,0.2231,0.7103,0.994]},{"id":"d1","label":"tv","confidence":0.3759,"bbox":[0.0002,0.0033,0.2983,0.4898]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.6049,"y":0.5289,"confidence":0.9992,"usable":true},"left_shoulder":{"x":0.5914,"y":0.708,"confidence":0.9908,"usable":true},"right_shoulder":{"x":0.2348,"y":0.8154,"confidence":0.978,"usable":true},"left_elbow":{"x":0.654,"y":0.9416,"confidence":0.4744,"usable":false},"right_elbow":{"x":0.1815,"y":1.0,"confidence":0.0021,"usable":false},"left_wrist":{"x":0.7464,"y":0.9714,"confidence":0.1927,"usable":false},"right_wrist":{"x":0.4242,"y":0.922,"confidence":0.019,"usable":false}}}]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

## challenge-raised

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"person","confidence":0.7927,"bbox":[0.1177,0.1289,0.6547,0.9955]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.5209,"y":0.4267,"confidence":0.9976,"usable":true},"left_shoulder":{"x":0.6099,"y":0.8078,"confidence":0.9131,"usable":true},"right_shoulder":{"x":0.2877,"y":0.7402,"confidence":0.995,"usable":true},"left_elbow":{"x":0.6213,"y":1.0,"confidence":0.0083,"usable":false},"right_elbow":{"x":0.1605,"y":1.0,"confidence":0.082,"usable":false},"left_wrist":{"x":0.5977,"y":0.8768,"confidence":0.0457,"usable":false},"right_wrist":{"x":0.2173,"y":0.8618,"confidence":0.164,"usable":false}}}]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"person","confidence":0.7927,"bbox":[0.1177,0.1289,0.6547,0.9955]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.5209,"y":0.4267,"confidence":0.9976,"usable":true},"left_shoulder":{"x":0.6099,"y":0.8078,"confidence":0.9131,"usable":true},"right_shoulder":{"x":0.2877,"y":0.7402,"confidence":0.995,"usable":true},"left_elbow":{"x":0.6213,"y":1.0,"confidence":0.0083,"usable":false},"right_elbow":{"x":0.1605,"y":1.0,"confidence":0.082,"usable":false},"left_wrist":{"x":0.5977,"y":0.8768,"confidence":0.0457,"usable":false},"right_wrist":{"x":0.2173,"y":0.8618,"confidence":0.164,"usable":false}}}]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

## challenge-remote

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"person","confidence":0.924,"bbox":[0.1461,0.1845,0.6469,0.9938]},{"id":"d1","label":"tie","confidence":0.4144,"bbox":[0.4163,0.8025,0.524,1.0]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.533,"y":0.4658,"confidence":0.9976,"usable":true},"left_shoulder":{"x":0.6099,"y":0.8397,"confidence":0.9158,"usable":true},"right_shoulder":{"x":0.2797,"y":0.7683,"confidence":0.993,"usable":true},"left_elbow":{"x":0.6198,"y":1.0,"confidence":0.0045,"usable":false},"right_elbow":{"x":0.1874,"y":1.0,"confidence":0.0234,"usable":false},"left_wrist":{"x":0.6101,"y":0.9374,"confidence":0.007,"usable":false},"right_wrist":{"x":0.3059,"y":0.9007,"confidence":0.0301,"usable":false}}}]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"person","confidence":0.924,"bbox":[0.1461,0.1845,0.6469,0.9938]},{"id":"d1","label":"tie","confidence":0.4144,"bbox":[0.4163,0.8025,0.524,1.0]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.533,"y":0.4658,"confidence":0.9976,"usable":true},"left_shoulder":{"x":0.6099,"y":0.8397,"confidence":0.9158,"usable":true},"right_shoulder":{"x":0.2797,"y":0.7683,"confidence":0.993,"usable":true},"left_elbow":{"x":0.6198,"y":1.0,"confidence":0.0045,"usable":false},"right_elbow":{"x":0.1874,"y":1.0,"confidence":0.0234,"usable":false},"left_wrist":{"x":0.6101,"y":0.9374,"confidence":0.007,"usable":false},"right_wrist":{"x":0.3059,"y":0.9007,"confidence":0.0301,"usable":false}}}]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

## challenge-screen

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"tv","confidence":0.6066,"bbox":[0.0,0.0016,0.2592,0.4821]},{"id":"d1","label":"person","confidence":0.3821,"bbox":[0.5876,0.732,0.9036,0.9961]}],"poses":[]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"tv","confidence":0.6066,"bbox":[0.0,0.0016,0.2592,0.4821]},{"id":"d1","label":"person","confidence":0.3821,"bbox":[0.5876,0.732,0.9036,0.9961]}],"poses":[]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

## heldout-b-rest

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"person","confidence":0.7834,"bbox":[0.1706,0.1676,0.7794,0.9914]},{"id":"d1","label":"tv","confidence":0.3985,"bbox":[0.0001,0.0019,0.2912,0.4784]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.5568,"y":0.5587,"confidence":0.9987,"usable":true},"left_shoulder":{"x":0.6273,"y":0.8211,"confidence":0.8945,"usable":true},"right_shoulder":{"x":0.2672,"y":0.8124,"confidence":0.9865,"usable":true},"left_elbow":{"x":0.644,"y":0.9913,"confidence":0.0212,"usable":false},"right_elbow":{"x":0.2123,"y":1.0,"confidence":0.0057,"usable":false},"left_wrist":{"x":0.689,"y":0.8625,"confidence":0.1207,"usable":false},"right_wrist":{"x":0.4086,"y":0.9586,"confidence":0.0376,"usable":false}}}]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"person","confidence":0.7834,"bbox":[0.1706,0.1676,0.7794,0.9914]},{"id":"d1","label":"tv","confidence":0.3985,"bbox":[0.0001,0.0019,0.2912,0.4784]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.5568,"y":0.5587,"confidence":0.9987,"usable":true},"left_shoulder":{"x":0.6273,"y":0.8211,"confidence":0.8945,"usable":true},"right_shoulder":{"x":0.2672,"y":0.8124,"confidence":0.9865,"usable":true},"left_elbow":{"x":0.644,"y":0.9913,"confidence":0.0212,"usable":false},"right_elbow":{"x":0.2123,"y":1.0,"confidence":0.0057,"usable":false},"left_wrist":{"x":0.689,"y":0.8625,"confidence":0.1207,"usable":false},"right_wrist":{"x":0.4086,"y":0.9586,"confidence":0.0376,"usable":false}}}]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

## heldout-b-raised

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"person","confidence":0.7349,"bbox":[0.0817,0.0741,0.6637,0.9937]},{"id":"d1","label":"tv","confidence":0.4805,"bbox":[0.0,0.0037,0.2981,0.4828]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.4959,"y":0.4108,"confidence":0.9968,"usable":true},"left_shoulder":{"x":0.6174,"y":0.8355,"confidence":0.8909,"usable":true},"right_shoulder":{"x":0.3065,"y":0.8084,"confidence":0.9505,"usable":true},"left_elbow":{"x":0.6431,"y":1.0,"confidence":0.0049,"usable":false},"right_elbow":{"x":0.2606,"y":1.0,"confidence":0.0065,"usable":false},"left_wrist":{"x":0.6263,"y":0.9159,"confidence":0.019,"usable":false},"right_wrist":{"x":0.2717,"y":0.9136,"confidence":0.0394,"usable":false}}}]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"person","confidence":0.7349,"bbox":[0.0817,0.0741,0.6637,0.9937]},{"id":"d1","label":"tv","confidence":0.4805,"bbox":[0.0,0.0037,0.2981,0.4828]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.4959,"y":0.4108,"confidence":0.9968,"usable":true},"left_shoulder":{"x":0.6174,"y":0.8355,"confidence":0.8909,"usable":true},"right_shoulder":{"x":0.3065,"y":0.8084,"confidence":0.9505,"usable":true},"left_elbow":{"x":0.6431,"y":1.0,"confidence":0.0049,"usable":false},"right_elbow":{"x":0.2606,"y":1.0,"confidence":0.0065,"usable":false},"left_wrist":{"x":0.6263,"y":0.9159,"confidence":0.019,"usable":false},"right_wrist":{"x":0.2717,"y":0.9136,"confidence":0.0394,"usable":false}}}]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

## heldout-b-down

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"person","confidence":0.9247,"bbox":[0.1399,0.0762,0.6416,0.9931]},{"id":"d1","label":"tv","confidence":0.3583,"bbox":[0.0,0.0031,0.295,0.4769]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.4861,"y":0.4442,"confidence":0.9974,"usable":true},"left_shoulder":{"x":0.602,"y":0.8156,"confidence":0.9247,"usable":true},"right_shoulder":{"x":0.2616,"y":0.7839,"confidence":0.9925,"usable":true},"left_elbow":{"x":0.6149,"y":1.0,"confidence":0.0092,"usable":false},"right_elbow":{"x":0.1895,"y":1.0,"confidence":0.0145,"usable":false},"left_wrist":{"x":0.5756,"y":0.9156,"confidence":0.0081,"usable":false},"right_wrist":{"x":0.2937,"y":0.9107,"confidence":0.0126,"usable":false}}},{"id":"p1","keypoints":{"nose":{"x":0.4873,"y":0.4456,"confidence":0.9971,"usable":true},"left_shoulder":{"x":0.5996,"y":0.8154,"confidence":0.9344,"usable":true},"right_shoulder":{"x":0.2613,"y":0.7776,"confidence":0.991,"usable":true},"left_elbow":{"x":0.6205,"y":1.0,"confidence":0.0111,"usable":false},"right_elbow":{"x":0.1888,"y":1.0,"confidence":0.0192,"usable":false},"left_wrist":{"x":0.6014,"y":0.9281,"confidence":0.0111,"usable":false},"right_wrist":{"x":0.2978,"y":0.9106,"confidence":0.0267,"usable":false}}}]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"person","confidence":0.9247,"bbox":[0.1399,0.0762,0.6416,0.9931]},{"id":"d1","label":"tv","confidence":0.3583,"bbox":[0.0,0.0031,0.295,0.4769]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.4861,"y":0.4442,"confidence":0.9974,"usable":true},"left_shoulder":{"x":0.602,"y":0.8156,"confidence":0.9247,"usable":true},"right_shoulder":{"x":0.2616,"y":0.7839,"confidence":0.9925,"usable":true},"left_elbow":{"x":0.6149,"y":1.0,"confidence":0.0092,"usable":false},"right_elbow":{"x":0.1895,"y":1.0,"confidence":0.0145,"usable":false},"left_wrist":{"x":0.5756,"y":0.9156,"confidence":0.0081,"usable":false},"right_wrist":{"x":0.2937,"y":0.9107,"confidence":0.0126,"usable":false}}},{"id":"p1","keypoints":{"nose":{"x":0.4873,"y":0.4456,"confidence":0.9971,"usable":true},"left_shoulder":{"x":0.5996,"y":0.8154,"confidence":0.9344,"usable":true},"right_shoulder":{"x":0.2613,"y":0.7776,"confidence":0.991,"usable":true},"left_elbow":{"x":0.6205,"y":1.0,"confidence":0.0111,"usable":false},"right_elbow":{"x":0.1888,"y":1.0,"confidence":0.0192,"usable":false},"left_wrist":{"x":0.6014,"y":0.9281,"confidence":0.0111,"usable":false},"right_wrist":{"x":0.2978,"y":0.9106,"confidence":0.0267,"usable":false}}}]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

## heldout-food

### A, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### J, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
{"detections":[{"id":"d0","label":"person","confidence":0.9012,"bbox":[0.1394,0.1813,0.8824,0.9955]},{"id":"d1","label":"tv","confidence":0.626,"bbox":[0.0,0.0037,0.3007,0.4938]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.5927,"y":0.517,"confidence":0.9994,"usable":true},"left_shoulder":{"x":0.5949,"y":0.6894,"confidence":0.9918,"usable":true},"right_shoulder":{"x":0.2389,"y":0.8233,"confidence":0.9806,"usable":true},"left_elbow":{"x":0.6592,"y":0.9319,"confidence":0.441,"usable":false},"right_elbow":{"x":0.1828,"y":1.0,"confidence":0.0033,"usable":false},"left_wrist":{"x":0.7311,"y":0.9485,"confidence":0.1089,"usable":false},"right_wrist":{"x":0.4115,"y":0.9162,"confidence":0.018,"usable":false}}}]}
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

### B, repetitions 0, 1

```text
A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. USER: <image>
Fallible measurements of this exact image (normalized coordinates; low-confidence points are uncertain): {"detections":[{"id":"d0","label":"person","confidence":0.9012,"bbox":[0.1394,0.1813,0.8824,0.9955]},{"id":"d1","label":"tv","confidence":0.626,"bbox":[0.0,0.0037,0.3007,0.4938]}],"poses":[{"id":"p0","keypoints":{"nose":{"x":0.5927,"y":0.517,"confidence":0.9994,"usable":true},"left_shoulder":{"x":0.5949,"y":0.6894,"confidence":0.9918,"usable":true},"right_shoulder":{"x":0.2389,"y":0.8233,"confidence":0.9806,"usable":true},"left_elbow":{"x":0.6592,"y":0.9319,"confidence":0.441,"usable":false},"right_elbow":{"x":0.1828,"y":1.0,"confidence":0.0033,"usable":false},"left_wrist":{"x":0.7311,"y":0.9485,"confidence":0.1089,"usable":false},"right_wrist":{"x":0.4115,"y":0.9162,"confidence":0.018,"usable":false}}}]}
A missed detection does not prove absence. Boxes or nearby wrists do not prove holding. These measurements do not establish gaze, intent, or temporal actions. Use the image as primary evidence.
What is the person visibly doing? Answer in one short sentence using only clear visual evidence. Do not invent objects, actions, or intentions. If hands are not visible, do not describe what they are holding. ASSISTANT:
```

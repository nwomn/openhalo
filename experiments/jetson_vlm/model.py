"""Ollama protocol and the model-task ablation. No UI or capture ownership."""
import base64
import json
import time
import urllib.request


def runtime_info(config):
    """Read-only model identity/allocation for reproducible runs."""
    result = {}
    for name in ("version", "tags", "ps"):
        with urllib.request.urlopen(config.endpoint + "/api/" + name, timeout=10) as response:
            data = json.load(response)
        result[name] = data if name == "version" else [
            model for model in data["models"] if model["name"] == config.model]
    return result


def task_spec(task):
    prompt = ("观察这张图片，用中文描述最多三个最显著的人、物体或可见动作。"
              "每条描述不超过20个汉字。只描述可见证据，不猜测身份、意图或画外内容。"
              "无法辨认时写‘无法判断’。按给定JSON格式输出items，每项含label。")
    properties = {"label": {"type": "string"}}
    required = ["label"]
    if task == "grounded":
        prompt += ("每项还需bbox：[左,上,右,下]，用0到1000归一化坐标，"
                   "框住该描述对应的可见主体，左上角为原点。")
        properties["bbox"] = {"type": "array", "items": {"type": "number"},
                              "minItems": 4, "maxItems": 4}
        required.append("bbox")
    schema = {"type": "object", "properties": {"items": {"type": "array",
              "maxItems": 3, "items": {"type": "object", "properties": properties,
              "required": required, "additionalProperties": False}}},
              "required": ["items"], "additionalProperties": False}
    return prompt, schema


def parse_result(text, task):
    items = json.loads(text)["items"]
    if not isinstance(items, list) or len(items) > 3:
        raise ValueError("Expected at most three items")
    for item in items:
        if not isinstance(item["label"], str):
            raise ValueError("label must be a string")
        if task == "grounded":
            box = item["bbox"]
            if len(box) != 4 or not all(type(v) in (int, float) and 0 <= v <= 1000 for v in box):
                raise ValueError("bbox must contain four numbers in [0,1000]")
            x1, y1, x2, y2 = box
            if x2 <= x1 or y2 <= y1:
                raise ValueError("bbox must have positive area")
    return items


def infer(config, jpeg):
    prompt, schema = task_spec(config.task)
    payload = {"model": config.model, "stream": True, "format": schema,
               "keep_alive": "5m", "messages": [{"role": "user", "content": prompt,
               "images": [base64.b64encode(jpeg).decode("ascii")]}],
               "options": {"temperature": config.temperature, "seed": config.seed,
               "num_ctx": config.context, "num_predict": config.max_tokens}}
    request = urllib.request.Request(config.endpoint + "/api/chat",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    start, first = time.perf_counter(), None
    text, final = "", None
    with urllib.request.urlopen(request, timeout=180) as response:
        for line in response:
            part = json.loads(line)
            if "error" in part:
                raise RuntimeError(part["error"])
            content = part.get("message", {}).get("content", "")
            if content and first is None:
                first = time.perf_counter() - start
            text += content
            if part.get("done"):
                final = part
    if final is None:
        raise RuntimeError("Ollama stream ended without completion")
    metrics = {"request_s": time.perf_counter() - start, "first_content_s": first,
               "output_tokens": final.get("eval_count"),
               "input_tokens": final.get("prompt_eval_count"),
               "done_reason": final.get("done_reason")}
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        metrics[key.replace("_duration", "_s")] = final.get(key, 0) / 1e9
    return text, metrics

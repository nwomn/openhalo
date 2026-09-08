import io
import json
import unittest
from unittest.mock import patch

from config import Config
from model import infer, parse_result, task_spec


class ModelContractTest(unittest.TestCase):
    def test_display_is_not_a_model_factor(self):
        events = [
            {"message": {"content": '{"items":[]}'}, "done": False},
            {"message": {"content": ""}, "done": True, "eval_count": 8}]
        payloads = []
        def open_request(request, **kwargs):
            payloads.append(json.loads(request.data))
            return io.BytesIO(b"\n".join(json.dumps(e).encode() for e in events))
        with patch("urllib.request.urlopen", side_effect=open_request):
            for display in ("boxes", "subtitles"):
                raw, metrics = infer(Config(task="grounded", display=display), b"jpeg")
                self.assertEqual(parse_result(raw, "grounded"), [])
                self.assertEqual(metrics["output_tokens"], 8)
        self.assertEqual(payloads[0], payloads[1])

    def test_grounding_changes_only_task_contract(self):
        prompt, schema = task_spec("caption")
        grounded_prompt, grounded = task_spec("grounded")
        self.assertTrue(grounded_prompt.startswith(prompt))
        self.assertNotIn("bbox", schema["properties"]["items"]["items"]["properties"])
        self.assertIn("bbox", grounded["properties"]["items"]["items"]["required"])

    def test_invalid_coordinates_are_not_silently_repaired(self):
        for box in ([900, 100, 20, 400], [0, 0, 1001, 500], [0, 0, 0, 100]):
            with self.assertRaises(ValueError):
                parse_result(json.dumps({"items": [{"label": "人", "bbox": box}]}), "grounded")

    def test_truncated_stream_is_failure(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"message":{"content":"{"}}\n')):
            with self.assertRaisesRegex(RuntimeError, "without completion"):
                infer(Config(), b"jpeg")


if __name__ == "__main__":
    unittest.main()

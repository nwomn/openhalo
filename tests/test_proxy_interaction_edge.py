import unittest
from email.message import Message

from device_edge.proxy.adapter import AdapterProbe
from device_edge.proxy.adapter import BoundedFrameStore
from device_edge.proxy.adapter import EspKvmHttpAdapter
from device_edge.proxy.contracts import CapabilityAvailability
from device_edge.proxy.contracts import CapturedFrame
from device_edge.proxy.contracts import KEYBOARD_CAPABILITY
from device_edge.proxy.contracts import POINTER_CAPABILITY
from device_edge.proxy.edge import ProxyInteractionEdge


TEST_AUDIENCE = "wss://runtime.example/openhalo/edge"


def capability_states(
    *,
    screen: str = "available",
    keyboard: str = "available",
    pointer: str = "available",
) -> dict[str, CapabilityAvailability]:
    def state(value: str, reason: str) -> CapabilityAvailability:
        return CapabilityAvailability(value, None if value == "available" else reason)

    return {
        "screen": state(screen, "no_video_signal"),
        "audio": CapabilityAvailability("unavailable", "not_supported"),
        "keyboard": state(keyboard, "no_usb_target"),
        "pointer": state(pointer, "no_usb_target"),
        "virtual_media": CapabilityAvailability("unavailable", "not_enabled"),
        "power": CapabilityAvailability("unavailable", "not_enabled"),
    }


class FakeProxyAdapter:
    adapter_id = "fake-adapter-1"
    adapter_kind = "fake-proxy-v1"
    requirements = ("video", "usb-hid")
    supported_target_classes = frozenset({"desktop", "tablet"})

    def __init__(self, capabilities=None) -> None:
        self.capabilities = capabilities or capability_states()
        self.calls = []

    def probe(self) -> AdapterProbe:
        return AdapterProbe(self.capabilities, {"fake": True})

    def capture_frame(self) -> CapturedFrame:
        return CapturedFrame(
            evidence_ref="proxy-evidence://fake-adapter-1/screen/abc",
            captured_at="2026-08-24T10:00:01Z",
            width=1280,
            height=720,
            mime_type="image/jpeg",
            size_bytes=1024,
            sha256="a" * 64,
            capture_latency_ms=87,
        )

    def execute_keyboard(self, payload: dict) -> dict:
        self.calls.append(("keyboard", payload))
        return {"ok": True}

    def execute_pointer(self, payload: dict) -> dict:
        self.calls.append(("pointer", payload))
        return {"ok": True}


def build_edge(adapter=None, target_class="tablet") -> ProxyInteractionEdge:
    return ProxyInteractionEdge(
        device_id="proxy-edge-1",
        audience=TEST_AUDIENCE,
        target_id="xiaomi-pad-1",
        surface_id="xiaomi-pad-1/display-0",
        target_class=target_class,
        adapter=adapter or FakeProxyAdapter(),
        observed_at="2026-08-24T10:00:00Z",
        native_device_id="android-edge-pad-1",
    )


class ProxyInteractionEdgeTests(unittest.TestCase):
    def test_uses_own_proxy_identity_and_explicit_target_relationship(self) -> None:
        edge = build_edge()

        connect = edge.build_connect_frame()
        registration = edge.build_capability_announce_frame()

        self.assertEqual(connect["device"]["device_id"], "proxy-edge-1")
        self.assertEqual(connect["device"]["device_type"], "proxy-interaction")
        observe = registration["capabilities"][0]
        self.assertEqual(observe["target_relationship"]["target_id"], "xiaomi-pad-1")
        self.assertEqual(
            observe["target_relationship"]["surface_id"],
            "xiaomi-pad-1/display-0",
        )
        exposed = {item["name"]: item for item in observe["exposed_capabilities"]}
        self.assertEqual(exposed["screen"]["state"], "available")
        self.assertEqual(exposed["virtual_media"]["state"], "unavailable")

    def test_attachment_observation_binds_native_and_proxy_provenance(self) -> None:
        edge = build_edge()

        frame = edge.build_attachment_observation_frame()
        observation = frame["observations"][0]

        self.assertEqual(frame["capability"], "proxy.interaction.observe")
        self.assertEqual(observation["name"], "proxy.target_attachment.v1")
        self.assertEqual(observation["context_disposition"], "structural")
        self.assertEqual(observation["value"]["native_device_id"], "android-edge-pad-1")
        self.assertEqual(observation["value"]["attachment_state"], "attached")

    def test_screen_observation_contains_body_free_evidence_reference(self) -> None:
        edge = build_edge()

        frame = edge.build_screen_observation_frame()
        observation = frame["observations"][0]

        self.assertEqual(observation["name"], "proxy.screen_frame.v1")
        self.assertEqual(
            observation["evidence_ref"],
            "proxy-evidence://fake-adapter-1/screen/abc",
        )
        self.assertEqual(observation["value"]["source_kind"], "human_visible_pixels")
        self.assertNotIn("body", observation)
        self.assertNotIn("image", observation["value"])
        self.assertNotIn("data", observation["value"])

    def test_incompatible_target_is_explicit_and_announces_no_input_actions(self) -> None:
        edge = build_edge(target_class="television")

        frame = edge.build_attachment_observation_frame()
        capabilities = edge.build_capability_announce_frame()["capabilities"]

        self.assertEqual(
            frame["observations"][0]["value"]["attachment_state"],
            "incompatible",
        )
        self.assertEqual(
            [item["name"] for item in capabilities],
            [
                "proxy.interaction.observe",
                "proxy.screen.features",
                "proxy.screen.profile.configure",
            ],
        )

    def test_degraded_target_does_not_announce_unavailable_hid_actions(self) -> None:
        adapter = FakeProxyAdapter(
            capability_states(keyboard="unavailable", pointer="unavailable")
        )
        edge = build_edge(adapter)

        capabilities = edge.build_capability_announce_frame()["capabilities"]
        attachment = edge.build_attachment_observation_frame()["observations"][0]

        self.assertEqual(attachment["value"]["attachment_state"], "degraded")
        self.assertEqual(
            [item["name"] for item in capabilities],
            [
                "proxy.interaction.observe",
                "proxy.screen.features",
                "proxy.screen.profile.configure",
                "proxy.screen.evidence.read",
            ],
        )

    def test_governed_keyboard_action_checks_target_and_preserves_correlation(self) -> None:
        adapter = FakeProxyAdapter()
        edge = build_edge(adapter)
        request = {
            "type": "action_request",
            "device_id": "proxy-edge-1",
            "request_id": "request-1",
            "interaction_id": "interaction-1",
            "interaction_turn_id": "turn-1",
            "action": {
                "capability": KEYBOARD_CAPABILITY,
                "payload": {
                    "target_id": "xiaomi-pad-1",
                    "surface_id": "xiaomi-pad-1/display-0",
                    "operation": "type",
                    "text": "hello",
                },
            },
        }

        result = edge.handle_action_request(request)

        self.assertEqual(result["result"]["status"], "ok")
        self.assertEqual(result["result"]["capability"], KEYBOARD_CAPABILITY)
        self.assertEqual(result["request_id"], "request-1")
        self.assertEqual(result["interaction_id"], "interaction-1")
        self.assertEqual(result["interaction_turn_id"], "turn-1")
        self.assertEqual(adapter.calls[0][0], "keyboard")

        request["action"]["payload"]["target_id"] = "another-target"
        rejected = edge.handle_action_request(request)
        self.assertEqual(rejected["result"]["reason"], "target_mismatch")
        self.assertEqual(len(adapter.calls), 1)

    def test_governed_pointer_action_rejects_wrong_surface_before_adapter(self) -> None:
        adapter = FakeProxyAdapter()
        edge = build_edge(adapter)

        result = edge.handle_action_request(
            {
                "type": "action_request",
                "device_id": "proxy-edge-1",
                "request_id": "request-2",
                "action": {
                    "capability": POINTER_CAPABILITY,
                    "payload": {
                        "target_id": "xiaomi-pad-1",
                        "surface_id": "wrong-surface",
                        "operation": "click",
                        "x": 0.5,
                        "y": 0.5,
                    },
                },
            }
        )

        self.assertEqual(result["result"]["status"], "error")
        self.assertEqual(result["result"]["reason"], "surface_mismatch")
        self.assertEqual(adapter.calls, [])


class FakeHttpResponse:
    def __init__(self, body: bytes, content_type: str) -> None:
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeHttpOpener:
    def __init__(self, responses: list[tuple[bytes, str]]) -> None:
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        body, content_type = self.responses.pop(0)
        return FakeHttpResponse(body, content_type)


class EspKvmHttpAdapterTests(unittest.TestCase):
    @staticmethod
    def json_response(value: dict) -> tuple[bytes, str]:
        import json

        return json.dumps(value).encode("utf-8"), "application/json"

    def test_probe_maps_video_and_usb_to_proxy_capability_states(self) -> None:
        opener = FakeHttpOpener(
            [
                self.json_response(
                    {
                        "signal": True,
                        "width": 1280,
                        "height": 720,
                        "codec": "mjpeg",
                        "fps": 24,
                    }
                ),
                self.json_response({"os": "android", "trace": "D D C0"}),
                self.json_response({"agent_api": True}),
            ]
        )
        adapter = EspKvmHttpAdapter(
            "esp-kvm-1",
            "http://192.168.4.1",
            opener=opener,
        )

        probe = adapter.probe()

        self.assertEqual(probe.capabilities["screen"].state, "available")
        self.assertEqual(probe.capabilities["keyboard"].state, "degraded")
        self.assertEqual(probe.capabilities["pointer"].state, "degraded")
        self.assertEqual(probe.capabilities["audio"].state, "unavailable")
        self.assertEqual(probe.details["usb"]["target_os"], "android")

    def test_probe_marks_agent_gated_capabilities_unavailable_when_disabled(self) -> None:
        opener = FakeHttpOpener(
            [
                self.json_response(
                    {
                        "signal": True,
                        "width": 1280,
                        "height": 720,
                        "codec": "mjpeg",
                        "fps": 24,
                    }
                ),
                self.json_response({"os": "android", "trace": "D D C0"}),
                self.json_response({"agent_api": False}),
            ]
        )
        adapter = EspKvmHttpAdapter(
            "esp-kvm-1",
            "http://192.168.4.1",
            opener=opener,
        )

        probe = adapter.probe()

        for name in ("screen", "keyboard", "pointer"):
            self.assertEqual(probe.capabilities[name].state, "unavailable")
            self.assertEqual(probe.capabilities[name].reason, "agent_api_disabled")

    def test_capture_keeps_jpeg_in_bounded_edge_local_store(self) -> None:
        jpeg = b"\xff\xd8fake-jpeg\xff\xd9"
        opener = FakeHttpOpener(
            [
                self.json_response(
                    {
                        "signal": True,
                        "width": 1280,
                        "height": 720,
                        "codec": "mjpeg",
                    }
                ),
                (jpeg, "image/jpeg"),
            ]
        )
        store = BoundedFrameStore(max_frames=1)
        adapter = EspKvmHttpAdapter(
            "esp-kvm-1",
            "http://192.168.4.1",
            opener=opener,
            frame_store=store,
            clock=lambda: "2026-08-24T10:00:02Z",
        )

        frame = adapter.capture_frame()

        self.assertEqual(frame.width, 1280)
        self.assertEqual(frame.height, 720)
        self.assertEqual(frame.captured_at, "2026-08-24T10:00:02Z")
        self.assertEqual(store.get(frame.evidence_ref), jpeg)
        self.assertTrue(frame.evidence_ref.startswith("proxy-evidence://esp-kvm-1/screen/"))

    def test_pointer_coordinates_are_mapped_to_adapter_hid_range(self) -> None:
        opener = FakeHttpOpener([self.json_response({"ok": True})])
        adapter = EspKvmHttpAdapter(
            "esp-kvm-1",
            "http://192.168.4.1",
            opener=opener,
        )

        result = adapter.execute_pointer(
            {"operation": "click", "x": 0.5, "y": 1.0, "button": "right"}
        )

        self.assertEqual(result, {"ok": True})
        request = opener.requests[0][0]
        self.assertEqual(request.full_url, "http://192.168.4.1/api/v1/hid/click")
        import json

        self.assertEqual(
            json.loads(request.data),
            {"x": 16384, "y": 32767, "button": "right"},
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass


PACKAGE = "dev.openhalo.android.edge"
ACTIVITY = f"{PACKAGE}/.MainActivity"
EVENT_PREFIX = "OPENHALO_EDGE_EVENT "


@dataclass
class DeviceEvidence:
    device_id: str
    connected: bool
    service_foreground: bool
    sent_observation: bool
    sent_capability_announce: bool
    action_result_ok: bool
    last_error: str
    events: list[dict]
    ui_texts: list[str]


def run_adb(args: list[str], serial: str | None = None, timeout: int = 15) -> str:
    command = ["adb"]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def list_devices() -> list[str]:
    output = run_adb(["devices"], timeout=10)
    devices = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def start_app(serial: str | None) -> None:
    run_adb(["shell", "am", "start", "-n", ACTIVITY], serial=serial, timeout=10)


def tap(serial: str | None, x: int, y: int) -> None:
    run_adb(["shell", "input", "tap", str(x), str(y)], serial=serial, timeout=10)


def dump_ui_texts(serial: str | None) -> list[str]:
    run_adb(["shell", "uiautomator", "dump", "/sdcard/openhalo-window.xml"], serial=serial)
    xml_text = run_adb(["shell", "cat", "/sdcard/openhalo-window.xml"], serial=serial)
    texts = []
    root = ET.fromstring(xml_text)
    for node in root.iter("node"):
        text = node.attrib.get("text", "")
        if text:
            texts.append(text)
    return texts


def collect_events(serial: str | None, lines: int = 2000) -> list[dict]:
    output = run_adb(["logcat", "-d", "-t", str(lines)], serial=serial, timeout=20)
    events = []
    for line in output.splitlines():
        if EVENT_PREFIX not in line:
            continue
        payload_text = line.split(EVENT_PREFIX, 1)[1].strip()
        try:
            events.append(json.loads(payload_text))
        except json.JSONDecodeError:
            continue
    return events


def wait_for_evidence(
    serial: str | None,
    timeout_seconds: int,
    require_action: bool,
) -> DeviceEvidence:
    deadline = time.monotonic() + timeout_seconds
    last_ui_texts: list[str] = []
    while time.monotonic() < deadline:
        events = collect_events(serial)
        try:
            last_ui_texts = dump_ui_texts(serial)
        except Exception:
            last_ui_texts = []
        evidence = build_evidence(events, last_ui_texts)
        if (
            evidence.connected
            and evidence.sent_capability_announce
            and evidence.sent_observation
            and (evidence.action_result_ok or not require_action)
        ):
            return evidence
        time.sleep(2)
    return build_evidence(collect_events(serial), last_ui_texts)


def build_evidence(events: list[dict], ui_texts: list[str]) -> DeviceEvidence:
    ui_joined = "\n".join(ui_texts)
    connected = any(event.get("event") == "connected" for event in events) or (
        "Connection" in ui_texts and "connected" in ui_texts
    )
    service_foreground = any(
        event.get("event") in {"service_start_requested", "connected"}
        or event.get("service_state") == "foreground"
        for event in events
    ) or ("Service" in ui_texts and "foreground" in ui_texts)
    sent_capability_announce = any(
        event.get("event") == "sent_frame"
        and event.get("frame_type") == "capability_announce"
        for event in events
    )
    sent_observation = any(
        event.get("event") == "sent_frame"
        and event.get("frame_type") == "observation_push"
        for event in events
    ) or "Sent mobile.context" in ui_joined
    action_result_ok = any(
        event.get("event") == "action_result"
        and event.get("capability") == "notification.show"
        and event.get("status") == "ok"
        for event in events
    ) or bool(re.search(r"notification\.show\s*->\s*ok", ui_joined))
    device_id = ""
    for text in ui_texts:
        if text.startswith("android-edge-"):
            device_id = text
            break
    last_error = "None"
    if "Last Error" in ui_texts:
        index = ui_texts.index("Last Error")
        if index + 1 < len(ui_texts):
            last_error = ui_texts[index + 1]
    return DeviceEvidence(
        device_id=device_id,
        connected=connected,
        service_foreground=service_foreground,
        sent_observation=sent_observation,
        sent_capability_announce=sent_capability_announce,
        action_result_ok=action_result_ok,
        last_error=last_error,
        events=events,
        ui_texts=ui_texts,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--require-action", action="store_true")
    parser.add_argument("--tap-connect", action="store_true")
    parser.add_argument("--tap-observations", action="store_true")
    args = parser.parse_args()

    devices = list_devices()
    if not devices:
        raise SystemExit("no adb device is online")
    serial = args.serial or devices[0]
    if serial not in devices:
        raise SystemExit(f"adb device is not online: {serial}")

    run_adb(["logcat", "-c"], serial=serial)
    start_app(serial)
    time.sleep(2)
    if args.tap_connect:
        tap(serial, 250, 1210)
        time.sleep(2)
    if args.tap_observations:
        tap(serial, 350, 1410)
        time.sleep(1)

    evidence = wait_for_evidence(
        serial=serial,
        timeout_seconds=args.timeout_seconds,
        require_action=args.require_action,
    )
    result = {
        "ok": (
            evidence.connected
            and evidence.service_foreground
            and evidence.sent_capability_announce
            and evidence.sent_observation
            and (evidence.action_result_ok or not args.require_action)
        ),
        "device_serial": serial,
        "android_edge_device_id": evidence.device_id,
        "connected": evidence.connected,
        "service_foreground": evidence.service_foreground,
        "sent_capability_announce": evidence.sent_capability_announce,
        "sent_observation": evidence.sent_observation,
        "action_result_ok": evidence.action_result_ok,
        "last_error": evidence.last_error,
        "events": evidence.events[-20:],
        "ui_texts": evidence.ui_texts,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

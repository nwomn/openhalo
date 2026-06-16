"""CLI runner for the v0 single-edge loop."""

from device_edge.session_client import SessionClient
from personal_runtime.gateway_server import RuntimeGateway


def run_cli_once(text: str, token: str = "dev-token") -> dict:
    gateway = RuntimeGateway(shared_token=token)
    client = SessionClient(
        device_id="desktop-dev-1",
        device_type="desktop-cli",
        token=token,
    )
    replies = gateway.run_roundtrip(
        [
            client.build_connect_frame(),
            client.build_capability_announce_frame(),
            client.build_text_event(text),
        ]
    )
    action_request = replies[-1]
    return client.handle_action_request(action_request)


def main() -> None:
    print("CLI edge ready. Type one line to send to the runtime:")
    text = input("> ").strip()
    result = run_cli_once(text)
    print(f"Action result: {result['result']['status']}")


if __name__ == "__main__":
    main()

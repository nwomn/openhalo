from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from tempfile import TemporaryDirectory

import pytest

from openhalo.home import PersonalHome
from openhalo.outbound_proxy import ProxyConfigurationError
from openhalo.outbound_proxy import ProbeResult
from openhalo.outbound_proxy import OutboundProxyManager
from openhalo.outbound_proxy import ProxyOperationError
from openhalo.outbound_proxy import build_runtime_environment
from openhalo.outbound_proxy import probe_http_endpoint
from openhalo.outbound_proxy import redact_proxy_url
from openhalo.outbound_proxy import validate_proxy_url


class _ProbeHandler(BaseHTTPRequestHandler):
    response_status = 401

    def do_GET(self):
        self.send_response(self.response_status)
        self.end_headers()

    def log_message(self, *_args):
        return


class _ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.request_seen = True
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args):
        return


@pytest.fixture
def probe_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/provider"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_validate_proxy_url_accepts_authenticated_http_proxy() -> None:
    endpoint = validate_proxy_url("http://alice:p%40ss@proxy.example:8080/")

    assert endpoint.url == "http://alice:p%40ss@proxy.example:8080/"
    assert endpoint.scheme == "http"
    assert endpoint.hostname == "proxy.example"
    assert endpoint.port == 8080
    assert endpoint.has_credentials is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "proxy.example:8080",
        "ftp://proxy.example:8080",
        "http:///missing-host",
        "http://proxy.example:8080/path",
        "http://proxy.example:8080?query=1",
        "http://proxy.example:0",
        "http://proxy.example:65536",
    ],
)
def test_validate_proxy_url_rejects_incomplete_or_unsupported_urls(value: str) -> None:
    with pytest.raises(ProxyConfigurationError):
        validate_proxy_url(value)


def test_redact_proxy_url_removes_proxy_credentials() -> None:
    assert redact_proxy_url("https://alice:secret@proxy.example:8443") == {
        "url": "https://proxy.example:8443",
        "scheme": "https",
        "host": "proxy.example",
        "port": 8443,
        "authentication": "configured",
    }


def test_build_runtime_environment_clears_inherited_proxy_and_sets_loopback_bypass() -> None:
    source = {
        "HTTP_PROXY": "http://inherited.invalid:8080",
        "HTTPS_PROXY": "http://inherited.invalid:8080",
        "ALL_PROXY": "socks5://inherited.invalid:1080",
        "NO_PROXY": "example.invalid",
        "http_proxy": "http://inherited.invalid:8080",
        "https_proxy": "http://inherited.invalid:8080",
        "all_proxy": "socks5://inherited.invalid:1080",
        "no_proxy": "example.invalid",
        "WS_PROXY": "http://inherited.invalid:8080",
        "WSS_PROXY": "http://inherited.invalid:8080",
        "unrelated": "preserved",
    }

    environment = build_runtime_environment(
        source,
        proxy_url="http://configured.example:8080",
    )

    assert environment["HTTP_PROXY"] == "http://configured.example:8080"
    assert environment["HTTPS_PROXY"] == "http://configured.example:8080"
    assert environment["http_proxy"] == "http://configured.example:8080"
    assert environment["https_proxy"] == "http://configured.example:8080"
    assert environment["NO_PROXY"] == "127.0.0.1,localhost,::1"
    assert environment["no_proxy"] == "127.0.0.1,localhost,::1"
    assert "ALL_PROXY" not in environment
    assert "all_proxy" not in environment
    assert "WS_PROXY" not in environment
    assert "WSS_PROXY" not in environment
    assert environment["unrelated"] == "preserved"


def test_build_runtime_environment_defaults_to_direct_without_proxy() -> None:
    environment = build_runtime_environment(
        {"HTTP_PROXY": "http://inherited.invalid:8080", "PATH": os.environ["PATH"]},
        proxy_url=None,
    )

    assert "HTTP_PROXY" not in environment
    assert "HTTPS_PROXY" not in environment
    assert "ALL_PROXY" not in environment
    assert environment["NO_PROXY"] == "127.0.0.1,localhost,::1"
    assert environment["PATH"] == os.environ["PATH"]


def test_probe_http_endpoint_counts_provider_http_error_as_reachable(probe_server: str) -> None:
    result = probe_http_endpoint(probe_server, proxy_url=None, timeout_s=2)

    assert result.state == "reachable"
    assert result.http_status == 401
    assert result.failure_class is None


def test_probe_http_endpoint_reports_connection_failure_without_raw_url() -> None:
    result = probe_http_endpoint(
        "http://127.0.0.1:1/provider",
        proxy_url=None,
        timeout_s=0.1,
    )

    assert result.state == "unreachable"
    assert result.failure_class == "connection_failure"
    assert "127.0.0.1:1" not in result.safe_reason


def test_probe_http_endpoint_routes_through_explicit_proxy() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
    server.request_seen = False
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = probe_http_endpoint(
            "http://provider.invalid/v1",
            proxy_url=f"http://127.0.0.1:{server.server_port}",
            timeout_s=2,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.state == "reachable"
    assert result.http_status == 204
    assert server.request_seen is True


def test_personal_home_persists_and_clears_outbound_proxy() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        home.initialize_runtime(host="127.0.0.1", port=8765)

        home.configure_outbound_proxy("http://alice:secret@proxy.example:8080")
        persisted = home.load_configuration()

        assert home.outbound_proxy_url() == "http://alice:secret@proxy.example:8080"
        assert persisted["runtime"]["outbound_proxy"] == {
            "url": "http://alice:secret@proxy.example:8080"
        }

        home.clear_outbound_proxy()

        assert home.outbound_proxy_url() is None
        assert "outbound_proxy" not in home.load_configuration()["runtime"]


def test_personal_home_rejects_invalid_proxy_without_replacing_existing_value() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        home.initialize_runtime(host="127.0.0.1", port=8765)
        home.configure_outbound_proxy("http://proxy.example:8080")
        original = home.config_path.read_text(encoding="utf-8")

        with pytest.raises(ProxyConfigurationError):
            home.configure_outbound_proxy("ftp://proxy.example:8080")

        assert home.config_path.read_text(encoding="utf-8") == original


class _FakeSupervisor:
    def __init__(self, *, fail_next_start: bool = False) -> None:
        self.running = True
        self.fail_next_start = fail_next_start
        self.calls: list[str] = []

    def status(self) -> dict:
        return {"state": "running" if self.running else "stopped", "pid": 900}

    def stop(self) -> dict:
        self.calls.append("stop")
        self.running = False
        return {"state": "stopping", "pid": 900}

    def wait_until_stopped(self) -> dict:
        self.calls.append("wait")
        return {"state": "stopped", "pid": None}

    def start(self) -> dict:
        self.calls.append("start")
        if self.fail_next_start:
            self.fail_next_start = False
            raise RuntimeError("candidate did not become ready")
        self.running = True
        return {"state": "running", "pid": 901}


def _manager(
    home: PersonalHome,
    supervisor: _FakeSupervisor,
    probe_result: ProbeResult,
) -> OutboundProxyManager:
    return OutboundProxyManager(
        home,
        supervisor_factory=lambda _: supervisor,
        provider_endpoint_resolver=lambda _: "http://provider.example/v1",
        probe=lambda url, proxy_url, timeout_s: probe_result,
    )


def test_proxy_manager_does_not_change_configuration_when_candidate_probe_fails() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        home.initialize_runtime(host="127.0.0.1", port=8765)
        home.configure_outbound_proxy("http://old.example:8080")
        supervisor = _FakeSupervisor()
        manager = _manager(
            home,
            supervisor,
            ProbeResult(
                state="unreachable",
                http_status=407,
                failure_class="proxy_authentication",
                safe_reason="proxy authentication was rejected",
                latency_ms=3,
            ),
        )

        with pytest.raises(ProxyOperationError) as error:
            manager.set("http://new.example:8080")

        assert error.value.failure_class == "proxy_authentication"
        assert home.outbound_proxy_url() == "http://old.example:8080"
        assert supervisor.calls == []


def test_proxy_manager_restarts_running_runtime_after_successful_set() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        home.initialize_runtime(host="127.0.0.1", port=8765)
        supervisor = _FakeSupervisor()
        manager = _manager(
            home,
            supervisor,
            ProbeResult("reachable", 401, None, "provider endpoint responded", 4),
        )

        result = manager.set("http://new.example:8080")

        assert result == {
            "authentication": "none",
            "changed": True,
            "proxy_url": "http://new.example:8080",
            "runtime_restarted": True,
            "state": "configured",
        }
        assert home.outbound_proxy_url() == "http://new.example:8080"
        assert supervisor.calls == ["stop", "wait", "start"]


def test_proxy_manager_restores_old_configuration_when_candidate_restart_fails() -> None:
    with TemporaryDirectory() as directory:
        home = PersonalHome(Path(directory) / "home")
        home.initialize_runtime(host="127.0.0.1", port=8765)
        home.configure_outbound_proxy("http://old.example:8080")
        supervisor = _FakeSupervisor(fail_next_start=True)
        manager = _manager(
            home,
            supervisor,
            ProbeResult("reachable", 401, None, "provider endpoint responded", 4),
        )

        with pytest.raises(ProxyOperationError) as error:
            manager.set("http://new.example:8080")

        assert error.value.failure_class == "runtime_restart"
        assert home.outbound_proxy_url() == "http://old.example:8080"
        assert supervisor.calls == ["stop", "wait", "start", "start"]
        assert supervisor.running is True

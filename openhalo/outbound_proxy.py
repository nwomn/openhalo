"""Owner-managed outbound proxy configuration and safe HTTP probing."""

from __future__ import annotations

import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit


class ProxyConfigurationError(ValueError):
    """Raised when an outbound proxy URL is not supported."""


class ProxyOperationError(RuntimeError):
    """Raised when a proxy operation cannot be applied safely."""

    def __init__(
        self,
        operation: str,
        failure_class: str,
        safe_reason: str,
        *,
        rollback_failed: bool = False,
    ) -> None:
        super().__init__(safe_reason)
        self.operation = operation
        self.failure_class = failure_class
        self.safe_reason = safe_reason
        self.rollback_failed = rollback_failed


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    url: str
    scheme: str
    hostname: str
    port: int
    has_credentials: bool


@dataclass(frozen=True, slots=True)
class ProbeResult:
    state: str
    http_status: int | None
    failure_class: str | None
    safe_reason: str
    latency_ms: int


_PROXY_ENVIRONMENT_NAMES = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "WS_PROXY",
        "WSS_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "ws_proxy",
        "wss_proxy",
    }
)
_LOOPBACK_NO_PROXY = "127.0.0.1,localhost,::1"


class OutboundProxyManager:
    def __init__(
        self,
        home,
        *,
        supervisor_factory=None,
        provider_endpoint_resolver=None,
        probe=None,
        timeout_s: float = 10.0,
    ) -> None:
        self.home = home
        if supervisor_factory is None:
            from openhalo.runtime_supervisor import RuntimeSupervisor

            supervisor_factory = RuntimeSupervisor
        self.supervisor_factory = supervisor_factory
        self.provider_endpoint_resolver = (
            provider_endpoint_resolver or _default_provider_endpoint_resolver
        )
        self.probe = probe or probe_http_endpoint
        self.timeout_s = timeout_s

    def show(self) -> dict:
        proxy_url = self.home.outbound_proxy_url()
        if proxy_url is None:
            return {
                "authentication": "none",
                "proxy_url": None,
                "state": "direct",
            }
        redacted = redact_proxy_url(proxy_url)
        return {
            "authentication": redacted["authentication"],
            "proxy_url": redacted["url"],
            "state": "configured",
        }

    def test(self) -> dict:
        proxy_url = self.home.outbound_proxy_url()
        result = self._probe(proxy_url)
        return self._probe_payload(proxy_url, result)

    def set(self, url: str) -> dict:
        try:
            candidate_url = validate_proxy_url(url).url
        except ProxyConfigurationError as exc:
            raise ProxyOperationError(
                "set",
                "invalid_configuration",
                "proxy URL is invalid",
            ) from exc
        current_url = self.home.outbound_proxy_url()
        result = self._probe(candidate_url)
        self._require_reachable("set", result)
        if current_url == candidate_url:
            return self._configured_result(candidate_url, changed=False, restarted=False)
        return self._apply(candidate_url, current_url)

    def clear(self) -> dict:
        current_url = self.home.outbound_proxy_url()
        result = self._probe(None)
        self._require_reachable("clear", result)
        if current_url is None:
            return {
                "changed": False,
                "proxy_url": None,
                "runtime_restarted": False,
                "state": "direct",
            }
        return self._apply(None, current_url)

    def _probe(self, proxy_url: str | None) -> ProbeResult:
        try:
            endpoint = self.provider_endpoint_resolver(self.home)
            return self.probe(
                endpoint,
                proxy_url=proxy_url,
                timeout_s=self.timeout_s,
            )
        except ProxyOperationError:
            raise
        except Exception as exc:
            raise ProxyOperationError(
                "test",
                "invalid_configuration",
                "Runtime Provider configuration is invalid",
            ) from exc

    def _require_reachable(self, operation: str, result: ProbeResult) -> None:
        if result.state == "reachable":
            return
        raise ProxyOperationError(
            operation,
            result.failure_class or "upstream_failure",
            result.safe_reason,
        )

    def _apply(self, candidate_url: str | None, previous_url: str | None) -> dict:
        supervisor = self.supervisor_factory(self.home)
        was_running = supervisor.status().get("state") == "running"
        if was_running:
            supervisor.stop()
            supervisor.wait_until_stopped()
        try:
            if candidate_url is None:
                self.home.clear_outbound_proxy()
            else:
                self.home.configure_outbound_proxy(candidate_url)
            if was_running:
                supervisor.start()
        except Exception as exc:
            try:
                if previous_url is None:
                    self.home.clear_outbound_proxy()
                else:
                    self.home.configure_outbound_proxy(previous_url)
                if was_running:
                    supervisor.start()
            except Exception as rollback_exc:
                raise ProxyOperationError(
                    "apply",
                    "rollback_failed",
                    "Runtime proxy change failed and rollback did not complete",
                    rollback_failed=True,
                ) from rollback_exc
            raise ProxyOperationError(
                "apply",
                "runtime_restart",
                "Runtime proxy change failed; previous configuration restored",
            ) from exc
        if candidate_url is None:
            return {
                "changed": True,
                "proxy_url": None,
                "runtime_restarted": was_running,
                "state": "direct",
            }
        return self._configured_result(
            candidate_url,
            changed=True,
            restarted=was_running,
        )

    @staticmethod
    def _configured_result(url: str, *, changed: bool, restarted: bool) -> dict:
        redacted = redact_proxy_url(url)
        return {
            "authentication": redacted["authentication"],
            "changed": changed,
            "proxy_url": redacted["url"],
            "runtime_restarted": restarted,
            "state": "configured",
        }

    @staticmethod
    def _probe_payload(proxy_url: str | None, result: ProbeResult) -> dict:
        payload = {
            "latency_ms": result.latency_ms,
            "mode": "proxy" if proxy_url is not None else "direct",
            "state": result.state,
        }
        if result.http_status is not None:
            payload["http_status"] = result.http_status
        if result.failure_class is not None:
            payload["failure_class"] = result.failure_class
            payload["reason"] = result.safe_reason
        return payload


def validate_proxy_url(value: str) -> ProxyEndpoint:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProxyConfigurationError("proxy URL must be a complete URL")
    if any(character in value for character in "\r\n\x00"):
        raise ProxyConfigurationError("proxy URL contains unsafe control characters")

    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ProxyConfigurationError("proxy URL must use http or https")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ProxyConfigurationError("proxy URL must not contain a path or query")
    if not parsed.hostname:
        raise ProxyConfigurationError("proxy URL must include a host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ProxyConfigurationError("proxy URL has an invalid port") from exc
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    if not 1 <= port <= 65535:
        raise ProxyConfigurationError("proxy URL has an invalid port")
    if parsed.password is not None and parsed.username is None:
        raise ProxyConfigurationError("proxy URL credentials are incomplete")
    return ProxyEndpoint(
        url=value,
        scheme=parsed.scheme.lower(),
        hostname=parsed.hostname,
        port=port,
        has_credentials=parsed.username is not None,
    )


def redact_proxy_url(value: str) -> dict:
    endpoint = validate_proxy_url(value)
    host = endpoint.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return {
        "url": f"{endpoint.scheme}://{host}:{endpoint.port}",
        "scheme": endpoint.scheme,
        "host": endpoint.hostname,
        "port": endpoint.port,
        "authentication": "configured" if endpoint.has_credentials else "none",
    }


def build_runtime_environment(
    source: dict[str, str],
    *,
    proxy_url: str | None,
) -> dict[str, str]:
    environment = {
        name: value
        for name, value in source.items()
        if name not in _PROXY_ENVIRONMENT_NAMES
    }
    environment["NO_PROXY"] = _LOOPBACK_NO_PROXY
    environment["no_proxy"] = _LOOPBACK_NO_PROXY
    if proxy_url is not None:
        endpoint = validate_proxy_url(proxy_url)
        environment["HTTP_PROXY"] = endpoint.url
        environment["HTTPS_PROXY"] = endpoint.url
        environment["http_proxy"] = endpoint.url
        environment["https_proxy"] = endpoint.url
    return environment


def probe_http_endpoint(
    url: str,
    *,
    proxy_url: str | None,
    timeout_s: float,
) -> ProbeResult:
    started = time.monotonic()
    try:
        if proxy_url is None:
            handler = urllib.request.ProxyHandler({})
        else:
            endpoint = validate_proxy_url(proxy_url)
            handler = urllib.request.ProxyHandler(
                {"http": endpoint.url, "https": endpoint.url}
            )
        opener = urllib.request.build_opener(handler)
        request = urllib.request.Request(
            url,
            headers={
                "Range": "bytes=0-0",
                "User-Agent": "openhalo-runtime-probe/0.1",
            },
            method="GET",
        )
        with opener.open(request, timeout=timeout_s) as response:
            status = int(response.status)
        return _reachable_result(status, started)
    except urllib.error.HTTPError as exc:
        return _http_error_result(exc.code, started)
    except Exception as exc:
        return ProbeResult(
            state="unreachable",
            http_status=None,
            failure_class=_failure_class(exc),
            safe_reason=_safe_reason(exc),
            latency_ms=_latency_ms(started),
        )


def _reachable_result(status: int, started: float) -> ProbeResult:
    if status < 500:
        return ProbeResult(
            state="reachable",
            http_status=status,
            failure_class=None,
            safe_reason="provider endpoint responded",
            latency_ms=_latency_ms(started),
        )
    return ProbeResult(
        state="unreachable",
        http_status=status,
        failure_class="upstream_failure",
        safe_reason="provider endpoint returned an upstream failure",
        latency_ms=_latency_ms(started),
    )


def _http_error_result(status: int, started: float) -> ProbeResult:
    if status == 407:
        failure_class = "proxy_authentication"
        reason = "proxy authentication was rejected"
        state = "unreachable"
    elif status < 500:
        failure_class = None
        reason = "provider endpoint responded"
        state = "reachable"
    else:
        failure_class = "upstream_failure"
        reason = "provider endpoint returned an upstream failure"
        state = "unreachable"
    return ProbeResult(
        state=state,
        http_status=status,
        failure_class=failure_class,
        safe_reason=reason,
        latency_ms=_latency_ms(started),
    )


def _failure_class(error: Exception) -> str:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(error, ssl.SSLError):
        return "tls_failure"
    if isinstance(error, socket.gaierror):
        return "dns_failure"
    if isinstance(error, (ConnectionError, OSError)):
        return "connection_failure"
    if isinstance(error, ProxyConfigurationError):
        return "invalid_configuration"
    return "connection_failure"


def _safe_reason(error: Exception) -> str:
    if isinstance(error, ProxyConfigurationError):
        return "invalid proxy configuration"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "provider probe timed out"
    if isinstance(error, ssl.SSLError):
        return "provider TLS connection failed"
    if isinstance(error, socket.gaierror):
        return "provider hostname could not be resolved"
    return "provider endpoint could not be reached"


def _latency_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _default_provider_endpoint_resolver(home) -> str:
    from personal_runtime.model_provider import load_runtime_model_config
    from personal_runtime.model_provider import resolve_profile_config

    config = load_runtime_model_config(home.runtime_config_path)
    profile = resolve_profile_config(config, "proposal_formation")
    model = config.models[profile.model_ref]
    provider = config.providers[model.provider]
    return provider.base_url


__all__ = [
    "OutboundProxyManager",
    "ProbeResult",
    "ProxyConfigurationError",
    "ProxyEndpoint",
    "ProxyOperationError",
    "build_runtime_environment",
    "probe_http_endpoint",
    "redact_proxy_url",
    "validate_proxy_url",
]

"""Canonical Edge-owned registrations for the built-in Host and Terminal edges."""

from __future__ import annotations


def _observation(name: str, schema: dict, freshness: int, meaning: str, allowed: str, forbidden: str) -> dict:
    return {"name": name, "schema": schema, "freshness_seconds": freshness, "contract_version": 1,
            "machine_contract": {"value_schema": schema, "freshness_seconds": freshness},
            "semantic_contract": {"meaning": meaning, "permitted_inference": allowed, "must_not_infer": forbidden}}


def _action(name: str, schema: dict, side_effect: str, purpose: str, success: str, limitations: str) -> dict:
    return {"name": name, "direction": "runtime_to_edge", "kind": "action", "input_schema": schema,
            "side_effect": side_effect, "contract_version": 1,
            "machine_contract": {"input_schema": schema, "side_effect": side_effect, "result_states": ["ok", "error"], "requires_confirmation": False},
            "semantic_contract": {"purpose": purpose, "success_meaning": success, "limitations": limitations}}


def builtin_capability(name: str) -> dict:
    if name == "media.provider.configure":
        from device_edge.media_memory import media_provider_configure_capability
        return media_provider_configure_capability()
    if name == "media.memory.query":
        raise ValueError("media.memory.query must be registered with its source-bound Edge contract object.")
    if name == "text.input":
        return {"name": name, "direction": "edge_to_runtime", "kind": "event_source", "affordances": ["user_text"], "modality": "text", "privacy": "personal"}
    if name == "notification.show":
        schema = {"type": "object", "required": ["body"], "additionalProperties": False, "properties": {"title": {"type": "string"}, "body": {"type": "string", "minLength": 1}}}
        return {**_action(name, schema, "user_visible", "Deliver a private message on this Edge.", "The Edge accepted the delivery request.", "It does not prove the owner saw or understood it."), "affordances": ["notify_user", "deliver_private_text"], "modality": "visual_text", "privacy": "personal"}
    if name == "runtime.control":
        return _action(name, {"type": "object"}, "runtime_side_effect", "Request a bounded Runtime-host operation.", "The Host Edge reported the operation result.", "It does not prove downstream recovery without health evidence.")
    if name == "runtime.health":
        observations = [
            _observation("runtime.health_state", {"type": "string"}, 120, "Current Runtime health reported by this Host Edge.", "May guide recovery and availability decisions.", "Does not prove user impact or future availability."),
            _observation("runtime.process_pid", {"type": "integer", "nullable": True}, 120, "Reported Runtime process identifier.", "May correlate diagnostics.", "Does not prove process responsiveness."),
            _observation("runtime.process_present", {"type": "boolean"}, 120, "Whether the Host observes a Runtime process.", "May inform health assessment.", "Does not prove healthy service."),
            _observation("runtime.process_started_at", {"type": "string", "nullable": True}, 120, "Reported Runtime process start time.", "May inform restart detection.", "Does not prove continuous service."),
            _observation("runtime.process_memory_rss_bytes", {"type": "integer"}, 120, "Reported Runtime resident memory.", "May inform resource caution.", "Does not diagnose a cause.")]
    elif name == "host.metrics":
        observations = [_observation("host.cpu_load_ratio", {"type": "number"}, 120, "Current Host CPU load ratio.", "May inform resource caution.", "Does not prove application-specific cause or user-visible latency.")]
        observations += [_observation(n, s, 120, "Current Host resource metric.", "May inform resource caution.", "Does not identify the cause or user impact.") for n, s in (("host.memory_used_bytes", {"type": "integer"}), ("host.memory_available_bytes", {"type": "integer"}), ("host.memory_pressure", {"type": "string"}), ("host.net_rx_bytes", {"type": "integer"}), ("host.net_tx_bytes", {"type": "integer"}))]
    else:
        raise ValueError(f"No Edge-owned contract for capability {name!r}")
    return {"name": name, "direction": "edge_to_runtime", "kind": "observation_provider", "observations": observations}


def normalize_builtin_capabilities(capabilities: list[str | dict]) -> list[dict]:
    return [builtin_capability(item) if isinstance(item, str) else item for item in capabilities]

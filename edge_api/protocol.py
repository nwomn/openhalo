"""Public Edge API frame helpers.

This module is intentionally small so external edges can reuse the same frame
contract without importing Personal Runtime internals.
"""

API_VERSION = "edge.runtime.v2"

REQUIRED_TYPES = {
    "connect",
    "auth_challenge",
    "auth_proof",
    "connect_ok",
    "capability_announce",
    "event_push",
    "observation_push",
    "event_ack",
    "action_request",
    "action_result",
    "evidence_transfer",
    "understanding_update",
    "interaction_progress",
    "interaction_update",
    "error",
}


def validate_frame(frame: dict) -> dict:
    frame_type = frame.get("type")
    if frame_type not in REQUIRED_TYPES:
        raise ValueError(f"Unsupported frame type: {frame_type!r}")
    api_version = frame.get("api_version")
    if api_version is not None and api_version != API_VERSION:
        raise ValueError(f"Unsupported api_version: {api_version!r}")
    return frame


def with_api_version(frame: dict) -> dict:
    return {"api_version": API_VERSION, **frame}


def build_connect_frame(
    device_id: str,
    device_type: str,
    audience: str,
    pairing_code: str | None = None,
    public_key: str | None = None,
    display_name: str | None = None,
    role: str | None = None,
    session_id: str | None = None,
) -> dict:
    device = {
        "device_id": device_id,
        "device_type": device_type,
    }
    if role is not None:
        device["role"] = role
    frame = {
        "type": "connect",
        "device": device,
        "audience": audience,
    }
    if pairing_code is not None:
        if not public_key or not display_name:
            raise ValueError("Pairing connect requires public_key and display_name.")
        frame["auth"] = {
            "kind": "pairing",
            "pairing_code": pairing_code,
            "public_key": public_key,
            "display_name": display_name,
        }
    if session_id is not None:
        frame["session_id"] = session_id
    return with_api_version(frame)


def build_capability_announce_frame(
    device_id: str,
    capabilities: list[str | dict],
    session_id: str | None = None,
) -> dict:
    for capability in capabilities:
        validate_capability_registration(capability)
    frame = {
        "type": "capability_announce",
        "device_id": device_id,
        "capabilities": capabilities,
    }
    if session_id is not None:
        frame["session_id"] = session_id
    return with_api_version(frame)


def validate_capability_registration(capability: str | dict) -> str | dict:
    if isinstance(capability, str):
        raise ValueError("String capability registrations are not supported; announce a versioned capability contract object.")
    if not isinstance(capability, dict):
        raise ValueError("Capability registration must be a string or object.")
    name = capability.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Capability registration object requires a name.")
    direction = capability.get("direction")
    if direction is not None and direction not in {
        "edge_to_runtime",
        "runtime_to_edge",
        "bidirectional",
    }:
        raise ValueError(f"Unsupported capability direction: {direction!r}")
    input_schema = capability.get("input_schema")
    if input_schema is not None and not isinstance(input_schema, dict):
        raise ValueError("Capability input_schema must be an object.")
    process_contract = capability.get("process_contract")
    if process_contract is not None:
        _validate_process_contract(process_contract)
    _validate_capability_contracts(capability)
    observations = capability.get("observations", [])
    if observations is None:
        return capability
    if not isinstance(observations, list):
        raise ValueError("Capability observations must be a list.")
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("Observation registration must be an object.")
        observation_name = observation.get("name")
        if not isinstance(observation_name, str) or not observation_name:
            raise ValueError("Observation registration object requires a name.")
        schema = observation.get("schema")
        if schema is not None and not isinstance(schema, dict):
            raise ValueError("Observation schema must be an object.")
    return capability


def _validate_capability_contracts(capability: dict) -> None:
    """Validate the additive dual contract used by new rich registrations.

    ``machine_contract`` is the deterministic validation/execution surface.
    ``semantic_contract`` is the small, non-authoritative explanation supplied
    to Main Hermes.  Keeping them separate prevents model prose from becoming
    an execution permission or a replacement for schema validation.

    String capabilities and older rich registrations remain readable during
    migration.  A registration that opts into ``contract_version`` must supply
    both halves, which is the required form for newly authored contracts.
    """
    version = capability.get("contract_version")
    machine = capability.get("machine_contract")
    semantic = capability.get("semantic_contract")
    if version is None and machine is None and semantic is None:
        if capability.get("kind") == "action":
            raise ValueError("Action capability requires contract_version 1 dual contract.")
        for observation in capability.get("observations", []) or []:
            _validate_observation_contracts(observation)
        return
    if version != 1:
        raise ValueError("Capability contract_version must be 1.")
    if not isinstance(machine, dict) or not isinstance(semantic, dict):
        raise ValueError("Capability contract_version 1 requires machine_contract and semantic_contract objects.")
    kind = capability.get("kind")
    if kind == "action":
        if (
            machine.get("input_schema") != capability.get("input_schema")
            and machine.get("input_schema_binding") != "registration.input_schema"
        ):
            raise ValueError("Action machine_contract input_schema must equal capability input_schema.")
        for field in ("side_effect", "result_states"):
            if field not in machine:
                raise ValueError(f"Action machine_contract requires {field}.")
        required_semantic = ("purpose", "success_meaning", "limitations")
    elif kind == "observation_provider":
        required_semantic = ()
    else:
        return
    if any(not isinstance(semantic.get(field), str) or not semantic[field].strip() for field in required_semantic):
        raise ValueError("Capability semantic_contract is incomplete.")
    for observation in capability.get("observations", []) or []:
        _validate_observation_contracts(observation)


def _validate_observation_contracts(observation: dict) -> None:
    version = observation.get("contract_version")
    machine = observation.get("machine_contract")
    semantic = observation.get("semantic_contract")
    if version is None and machine is None and semantic is None:
        raise ValueError("Observation registration requires contract_version 1 dual contract.")
    if version != 1 or not isinstance(machine, dict) or not isinstance(semantic, dict):
        raise ValueError("Observation contract_version 1 requires machine_contract and semantic_contract objects.")
    if (
        machine.get("value_schema") != observation.get("schema")
        and machine.get("value_schema_binding") != "registration.schema"
    ):
        raise ValueError("Observation machine_contract value_schema must equal observation schema.")
    if machine.get("freshness_seconds") != observation.get("freshness_seconds"):
        raise ValueError("Observation machine_contract freshness_seconds must equal observation freshness_seconds.")
    for field in ("meaning", "permitted_inference", "must_not_infer"):
        if not isinstance(semantic.get(field), str) or not semantic[field].strip():
            raise ValueError("Observation semantic_contract is incomplete.")


def _validate_process_contract(contract: object) -> None:
    if not isinstance(contract, dict):
        raise ValueError("Capability process_contract must be an object.")
    if contract.get("continuation_policy") not in {"until_settled", "until_verified"}:
        raise ValueError("Capability process_contract requires a persistent continuation_policy.")
    watches = contract.get("watches")
    if not isinstance(watches, list) or not watches:
        raise ValueError("Capability process_contract requires at least one watch.")
    for watch in watches:
        if not isinstance(watch, dict):
            raise ValueError("Capability process_contract watch must be an object.")
        if not isinstance(watch.get("watch_id"), str) or not watch["watch_id"]:
            raise ValueError("Capability process_contract watch requires watch_id.")
        names = watch.get("observation_names")
        if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
            raise ValueError("Capability process_contract watch requires observation_names.")


def build_event_push_frame(
    device_id: str,
    capability: str,
    payload: dict,
    event_id: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    parent_event_id: str | None = None,
) -> dict:
    frame = {
        "type": "event_push",
        "device_id": device_id,
        "capability": capability,
        "payload": payload,
    }
    if event_id is not None:
        frame["event_id"] = event_id
    if trace_id is not None:
        frame["trace_id"] = trace_id
    if session_id is not None:
        frame["session_id"] = session_id
    if turn_id is not None:
        frame["turn_id"] = turn_id
    if parent_event_id is not None:
        frame["parent_event_id"] = parent_event_id
    return with_api_version(frame)


def build_observation_push_frame(
    device_id: str,
    capability: str,
    observations: list[dict],
    event_id: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    parent_event_id: str | None = None,
) -> dict:
    frame = {
        "type": "observation_push",
        "device_id": device_id,
        "capability": capability,
        "observations": observations,
        "payload": {"observations": observations},
    }
    if event_id is not None:
        frame["event_id"] = event_id
    if trace_id is not None:
        frame["trace_id"] = trace_id
    if session_id is not None:
        frame["session_id"] = session_id
    if turn_id is not None:
        frame["turn_id"] = turn_id
    if parent_event_id is not None:
        frame["parent_event_id"] = parent_event_id
    return with_api_version(frame)

"""Minimal response generation for the v0 runtime."""


def generate_reply(user_text: str, trace_recorder=None) -> str:
    reply = f"Runtime heard: {user_text}"
    if trace_recorder is not None:
        trace_recorder.record("AGENT", "generated reply", reply=reply)
    return reply

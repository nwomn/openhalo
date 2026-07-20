"""Editable first-run model configuration written into the personal home."""

DEFAULT_RUNTIME_CONFIG = """[llm.providers.openai_main]
adapter_type = "openai_compatible"
base_url = "https://api.openai.com/v1"
wire_api = "responses"
api_key = "replace-with-provider-api-key"
timeout_seconds = 30
default_headers = { "User-Agent" = "openhalo-runtime/0.1" }

[llm.models.default]
provider = "openai_main"
model_id = "replace-with-provider-model"
supports_structured_output = true
supports_tools = true

[llm.profiles.interactive_reply]
model_ref = "default"
provider_failure_behavior = "user_visible_error"

[llm.profiles.proposal_formation]
model_ref = "default"
provider_failure_behavior = "user_visible_error"

[llm.profiles.initiative_proposal]
model_ref = "default"
provider_failure_behavior = "user_visible_error"

[harness]
runner = "hermes"

[harness.hermes]
home = ".runtime/hermes"
max_agent_iterations = 6
allowed_hosts = []
max_research_calls = 3
research_timeout_seconds = 10
max_research_response_bytes = 80000
"""

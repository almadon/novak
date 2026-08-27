"""Injects Novak's persona into every request, per model, transparently.

This is the mechanism decision #21 exists for: the persona lives in one
place (prompts/) and is applied once, here, rather than copied into each
client's own config. No client-side change needed beyond pointing its base
URL at this router instead of at oMLX directly.

Registered via litellm_settings.callbacks in config.yaml, using
async_pre_call_hook rather than LiteLLM's newer CustomPromptManagement /
get_chat_completion_prompt API. That API is the one actually documented
for exactly this ("Custom Prompt Management"), and was tried first: its
own source (litellm/litellm_core_utils/litellm_logging.py,
get_custom_logger_for_prompt_management) confirms it should work with no
per-model config, falling back to any registered CustomPromptManagement
instance when no prompt_id is given. Registered a callback exactly per
LiteLLM's own reference implementation
(litellm/proxy/custom_prompt_management.py), confirmed the module loaded
at startup with a debug print, and confirmed the method was never called
across repeated real chat completions against ghcr.io/berriai/litellm:
main-stable. async_pre_call_hook is the older, plainer CustomLogger method
used for guardrails and rate limiting everywhere, and it does fire on
every request — checked the same way, not assumed from either mechanism's
documentation.
"""

import logging
from pathlib import Path

from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger("novak.persona_hook")

PROMPTS_DIR = Path("/prompts")

# model_name (the client-facing name in config.yaml's model_list) -> the
# prompts/ file that owns its persona. A model_name absent from this map
# passes through untouched, so adding a model here later without a mapped
# persona is a no-op, not an error.
PERSONA_MAP = {
    "chat": "novak-chat.md",
    "deep": "novak-chat.md",
    "ha-voice": "novak-voice.md",
}


def _load_persona(filename: str) -> str:
    """
    Every file in prompts/ carries a header block (title, which profile it
    serves, why) above a `---` separator, documented in
    docs/documentation-standard.md's own conventions — only the text after
    it is the actual persona a model should see. Falls back to the whole
    file if the separator is missing, rather than sending an empty system
    message silently.

    Re-read on every call, not cached at import time: an edit to prompts/
    takes effect on the next request, matching the promise `prompts/` is
    the live master copy, not a snapshot baked in at container start.
    """
    text = (PROMPTS_DIR / filename).read_text()
    _, _, body = text.partition("\n---\n")
    return body.strip() or text.strip()


class PersonaInjector(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        model = data.get("model")
        persona_file = PERSONA_MAP.get(model)
        if not persona_file:
            return data

        messages = data.get("messages") or []
        if messages and messages[0].get("role") == "system":
            # A client that sends its own system message is trusted over
            # the default — this is what lets a real debugging session or
            # a deliberately different client override the persona without
            # needing a flag or a second code path here.
            return data

        try:
            persona = _load_persona(persona_file)
        except OSError:
            # Fail open on the persona, not on the request. A missing or
            # unreadable prompts/ file should degrade to "no persona" for
            # this one call, the same as a model absent from PERSONA_MAP —
            # not take down inference for every client at once because one
            # file couldn't be read.
            logger.warning("could not read persona file %s for model %s", persona_file, model)
            return data

        data["messages"] = [{"role": "system", "content": persona}] + list(messages)
        return data


persona_injector = PersonaInjector()

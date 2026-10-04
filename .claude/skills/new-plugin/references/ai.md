# Plugins that call a language model

Read this when the plugin generates text with an LLM. **It carries no AI setup of its own**:
no API key field, no endpoint, no model list, no OAuth sign-in. It calls
`self.ai_complete()`, which uses the providers the user set up in **Settings → AI
Providers** (the same ones FiestaBot uses: OpenAI-compatible, Anthropic, OpenAI Responses;
pasted key or a sign-in with OpenRouter, Hugging Face, or ChatGPT). Full guide:
`docs/development/plugin-ai.md` in the core repo.

## The call (FiestaBoard 9.11.0)

```python
from src.plugins.base import AIError, AINotConfiguredError, AIRejectedError

result = self.ai_complete(
    messages,                 # "prompt" or [{"role": "system"|"user"|"assistant", "content": str}]
    provider_id=self.config.get("ai_provider") or None,  # None = FiestaBot's default
    model=None,               # None = the provider's default model
    temperature=None,         # 0.7
    max_tokens=None,          # 1500
    json=False,               # True: parsed object in result.data
)
result.text, result.data, result.model, result.provider_id, result.usage
```

- Sync and safe in `fetch_data`; `await self.ai_complete_async(...)` from async code.
- `AINotConfiguredError`: AI off, no provider, unknown `provider_id`, no model. Nothing sent.
  → "Set up AI in Settings → AI Providers."
- `AIRejectedError`: key or sign-in refused, or must sign in again (a signed-in `401` was
  already retried once). → "Reconnect the provider in Settings → AI Providers."
- `AIProviderError`: unreachable, error answer, empty or non-JSON reply.
- All are `AIError`. Catch them and return `PluginResult(available=False, error=...)`;
  `fetch_data` must never raise. `ValueError` means malformed `messages` (a plugin bug).
- Cache the result; never call the model on every render.

## The provider picker

```json
"ai_provider": {
  "type": "string", "title": "AI provider", "default": "",
  "description": "Leave empty for FiestaBot's default provider.",
  "ui:widget": "remote-options",
  "ui:options": {"options_id": "ai_providers", "searchable": true, "cache_seconds": 30}
}
```

Core answers `ai_providers` (every provider, every protocol); write no `get_options` for it.
If the plugin has its own `get_options`, end it with `return super().get_options(request)`.

## Existing plugins with their own key

A saved `api_key` (+ `api_base_url`, `model`) keeps working byte-for-byte and wins when set;
`ai_complete` is used only when it is empty. Never migrate or delete those settings. Remove
any plugin-level OpenRouter (or other AI) OAuth sign-in.

## Tests and version

- Patch the instance: `plugin.ai_complete = lambda *a, **k: AICompletion(text="HI",
  model="test-model", provider_id="test")` (`from src.ai.plugin_api import AICompletion`).
  Cover each exception → unavailable result, and that a saved `api_key` still takes the old path.
- `"fiestaboard_version": ">=9.11.0"` and CI pinned to match, or guard with
  `getattr(self, "ai_complete", None)` and import the exceptions inside that guard.

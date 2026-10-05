---
sidebar_position: 3
description: "Call a language model from a FiestaBoard plugin with ai_complete(): it uses the AI providers set up in Settings, including signed-in OpenRouter, Hugging Face and ChatGPT, so the plugin carries no AI setup of its own."
keywords: [FiestaBoard AI plugin, ai_complete, FiestaBot providers, LLM plugin, generative plugin, ai_providers picker, plugin development]
---

# Using FiestaBoard's AI Providers

A plugin that writes text with a language model does not need its own API key, endpoint, or sign-in. It calls `self.ai_complete(...)`, and FiestaBoard sends the request through the AI providers the user already set up in **Settings → AI Providers**, the same ones FiestaBot uses. That covers every protocol FiestaBoard speaks (OpenAI-compatible, Anthropic, and OpenAI Responses) and every way of connecting: a pasted key, or a sign-in with OpenRouter, Hugging Face, or ChatGPT.

**Requires FiestaBoard 9.11.0 or later.** Set `"fiestaboard_version": ">=9.11.0"`, or guard the call as shown in [Older FiestaBoard](#older-fiestaboard).

## The Short Version

```python
from src.plugins.base import AIError, AINotConfiguredError, AIRejectedError, PluginBase, PluginResult

def fetch_data(self) -> PluginResult:
    try:
        result = self.ai_complete(
            [
                {"role": "system", "content": "You write one short line for a split-flap board."},
                {"role": "user", "content": "A greeting for a rainy Monday."},
            ],
            provider_id=self.config.get("ai_provider") or None,  # None = FiestaBot's default
            max_tokens=60,
        )
    except AINotConfiguredError as exc:
        return PluginResult(available=False, error=f"Set up AI in Settings → AI Providers. ({exc})")
    except AIRejectedError as exc:
        return PluginResult(available=False, error=f"Reconnect the AI provider in Settings. ({exc})")
    except AIError as exc:  # unreachable, error answer, empty reply
        return PluginResult(available=False, error=str(exc))
    return PluginResult(available=True, data={"line": result.text})
```

## `ai_complete`

```python
self.ai_complete(
    messages,               # "a prompt" or [{"role": "system"|"user"|"assistant", "content": str}, ...]
    *,
    provider_id=None,       # None or "" = FiestaBot's default provider
    model=None,             # None = that provider's default model
    temperature=None,       # default 0.7; capped at 1.0 for Anthropic providers
    max_tokens=None,        # default 1500
    json=False,             # True: ask for one JSON object and parse it into result.data
    timeout=60.0,           # seconds
) -> AICompletion
```

It blocks until the answer arrives, so it is safe to call from `fetch_data`. Async code awaits `self.ai_complete_async(...)` with the same arguments.

The result has `.text`, `.model`, `.provider_id`, `.usage` (`prompt_tokens`, `completion_tokens`, `total_tokens`, any of which may be `None`), and `.data` (the parsed object when `json=True`). `str(result)` is the text.

With `model=None` and no model saved for the provider (a provider added with **Sign in** is saved before a model is picked), FiestaBoard uses the first model the provider lists, as FiestaBot's chat does, and remembers it for ten minutes.

A system message works with every protocol: for Anthropic it becomes the `system` field. With `json=True` FiestaBoard adds a system instruction asking for a single JSON object and extracts it from the reply even if the model wraps it in a code fence. It does not use a provider's JSON mode, because some local servers refuse it.

## Errors

Every failure is an `AIError`. Catch the three kinds separately to tell the user what to do:

| Exception | When | What to tell the user |
|-----------|------|-----------------------|
| `AINotConfiguredError` | AI is turned off in Settings, no provider is set up, `provider_id` names a provider that no longer exists, or the provider has no model saved and lists none. Nothing is sent. | Set up or turn on AI in **Settings → AI Providers**, or pick another provider. |
| `AIRejectedError` | The provider refused the key or sign-in (`401`), or a signed-in provider must be signed in again. A signed-in provider's `401` is retried once with a refreshed token before this is raised. | Reconnect the provider in **Settings → AI Providers**. |
| `AIProviderError` | The provider could not be reached, answered with an error, returned an empty reply, or (with `json=True`) returned something that is not a JSON object. | Try again later. The message carries the provider's own error text. |

A malformed `messages` argument raises `ValueError`: that is a bug in the plugin, not something to show the user.

Import the exceptions from `src.plugins.base` (or `src.ai.plugin_api`). `AIError` is the same class as core's `AIGenerationError`.

Don't call `ai_complete` on every render. Cache the result and refresh it on your plugin's own schedule; model calls are slow and may cost the user money.

## Letting the User Pick a Provider

Add a settings field with the `ai_providers` picker. Core answers it for you, so you don't write `get_options` for it:

```json
"ai_provider": {
  "type": "string",
  "title": "AI provider",
  "description": "Leave empty for FiestaBot's default provider.",
  "default": "",
  "ui:widget": "remote-options",
  "ui:options": {"options_id": "ai_providers", "searchable": true, "cache_seconds": 30, "placeholder": "FiestaBot's default provider"}
}
```

The picker lists every provider of every protocol, with its protocol, its default model, and whether it connects by signing in. When AI is turned off or nothing is set up, the field shows why instead of an empty list. Pass the saved value as `provider_id`; an empty string means the default provider.

If your plugin already implements `get_options` for other fields, end it with `return super().get_options(request)` so `ai_providers` still reaches core. `self.ai_providers()` returns the same list as dictionaries (`id`, `name`, `protocol`, `model`, `models`, `default`, `sign_in`), with no keys or tokens, for a plugin that wants to build its own.

## Keeping an Existing API Key Working

A plugin that used to take its own `api_key` (and `api_base_url`, `model`) must keep working for users who saved one. Use the saved key when it is set, exactly as before, and use `ai_complete` only when it is empty. Never migrate or delete the old settings.

```python
if self.config.get("api_key"):
    text = self._call_with_own_key()      # unchanged code path
else:
    text = self.ai_complete(prompt, provider_id=self.config.get("ai_provider") or None).text
```

Don't add an OAuth sign-in to a plugin for an AI service. Signing in to OpenRouter, Hugging Face, or ChatGPT happens once, in **Settings → AI Providers**, and every plugin shares it.

## Testing

Replace the method on the plugin instance; no network is involved:

```python
from src.ai.plugin_api import AICompletion, AIRejectedError

def test_writes_the_line(plugin):
    plugin.ai_complete = lambda *a, **k: AICompletion(text="HELLO", model="test-model", provider_id="test")
    assert plugin.fetch_data().data["line"] == "HELLO"

def test_rejected_sign_in_is_unavailable(plugin):
    def boom(*a, **k):
        raise AIRejectedError("Sign in to Test again in Settings → AI.")
    plugin.ai_complete = boom
    assert plugin.fetch_data().available is False
```

## Older FiestaBoard {#older-fiestaboard}

Before 9.11.0 there is no `ai_complete`. A plugin that must load on older cores checks first:

```python
complete = getattr(self, "ai_complete", None)
if complete is None:
    return PluginResult(available=False, error="Needs FiestaBoard 9.9 or later, or an API key in this plugin's settings.")
```

Import the exceptions inside the same guard, since `src.plugins.base` has no `AIError` before 9.11.0.

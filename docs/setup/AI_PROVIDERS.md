# AI Providers (Gen AI page generation)

FiestaBoard's **Gen AI** button (the Sparkles icon in the page editor)
lets you describe a page in natural language and have an LLM draft a
template for you. You then review and save the result yourself —
nothing is auto-saved.

FiestaBoard ships **without any bundled LLM credentials**. You bring
your own provider, your own API key, and your own model list. We
support any **OpenAI-compatible** chat-completions endpoint, which
covers OpenRouter, OpenAI, and most local servers (Ollama, LM Studio,
vLLM, llama.cpp, …).

## Configuration

1. Open **Settings → AI Providers**.
2. Toggle the top switch to **Enabled**.
3. Click **Add provider** and fill in:
   - **Name** — any label, e.g. `OpenRouter`.
   - **Base URL** — the chat-completions root, e.g.
     `https://openrouter.ai/api/v1`. Quick-pick buttons are provided
     for OpenRouter, OpenAI, and a local server.
   - **API Key** — paste the key. It is stored on this device's
     `data/config.json` and is masked (`***`) on read.
   - **Models** — type each model id and press Enter or click `+`
     (e.g. `openai/gpt-4o-mini`, `anthropic/claude-3.5-sonnet`).
   - **Default model** — picked automatically once you add at least
     one model.
4. (Optional) Click **Test connection** to send a one-token smoke
   test and confirm credentials and connectivity.
5. Click **Save changes**.

If you configure more than one provider, mark one as the default
using the **Make default** button.

## Recommended models

These all work well with the FiestaBoard prompt format:

| Provider     | Model                                  | Notes                              |
| ------------ | -------------------------------------- | ---------------------------------- |
| OpenRouter   | `openai/gpt-4o-mini`                   | Cheap, fast, reliable JSON output. |
| OpenRouter   | `anthropic/claude-3.5-sonnet`          | High-quality, slower.              |
| OpenAI       | `gpt-4o-mini`                          | Same as via OpenRouter.            |
| Local Ollama | `qwen2.5:14b-instruct` or larger       | Needs a model that follows JSON.   |

Smaller (≤ 7B) local models often struggle to emit valid JSON for
the FiestaBoard schema; if you see frequent "Could not parse JSON"
errors, switch to a larger or instruction-tuned model.

## Privacy

When you click **Generate**, FiestaBoard sends to the provider you
configured:

- The system prompt (board dimensions, character set rules, JSON
  schema).
- **Your prompt text.**
- **The variable list of all enabled plugins** (names + descriptions
  + max widths). This may include data such as transit station IDs
  or location names that you have configured.
- Up to a handful of example pages drawn from plugin manifests.
- Optionally, the **current draft page** (only when you tick "Use
  current page as a starting point").

API keys are stored locally and never sent to any FiestaBoard-hosted
service — there is no FiestaBoard AI proxy.

## Limitations (v1)

- OpenAI-compatible providers only. Raw Anthropic, Google, or Cohere
  APIs are not supported in v1; use OpenRouter to access them.
- No streaming UI: a single request/response.
- No automatic page creation or scheduling — you always review and
  click **Save**.
- No image/vision input.
- A modest per-process rate limit applies to `/pages/ai/generate` to
  protect against runaway clients (1 second between calls, 2
  concurrent).

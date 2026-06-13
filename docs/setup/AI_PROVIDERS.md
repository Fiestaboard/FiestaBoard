# AI Providers (Gen AI page generation)

FiestaBoard's **Gen AI** button (the Sparkles icon in the page editor)
lets you describe a page in natural language and have an LLM draft a
template for you. You then review and save the result yourself —
nothing is auto-saved.

FiestaBoard ships **without any bundled LLM credentials**. You bring
your own provider, your own API key, and your own model list.

Two protocols are supported out of the box:

- **OpenAI-compatible** chat-completions — one-click presets for
  OpenAI, OpenRouter, Groq, DeepSeek, Mistral, Together AI, and
  Fireworks AI, plus local servers Ollama, LM Studio, llama.cpp, and
  vLLM. Any other OpenAI-compatible endpoint works too.
- **Anthropic Messages API** — direct access to `api.anthropic.com`
  using a Claude API key.

## Choosing a provider

We recommend **[OpenRouter](https://openrouter.ai)** for most users.
A single API and key gives you access to hundreds of models from
OpenAI, Anthropic, Google, Meta, Mistral, DeepSeek, and others, with
pay-as-you-go billing and easy model switching from the FiestaBoard
dropdown.

> **Disclosure:** **FiestaBoard receives no referral fees,
> kickbacks, or affiliate commissions from OpenRouter.** There's no
> `?ref=` link in our docs and no partner agreement — we just like
> the product. If you'd prefer a direct relationship with one
> provider, any other preset works equally well.

If you already pay for OpenAI, Anthropic, or another provider,
prefer the matching preset and use your existing key. For
fully-local inference, pick Ollama, LM Studio, llama.cpp, or vLLM
(see the JSON-adherence caveat in the **Recommended models**
section).

## Quick setup with preset pills

In **Settings → AI Providers**, the **Quick presets** row gives you one-click pills for every supported provider, grouped into **Cloud** and **Local**. Clicking a pill auto-fills the **Name**, **Base URL**, and **Protocol** for that provider — you only have to paste your API key and add the model ids you want.

The current preset list, sourced from `web/src/components/settings/ai-settings.tsx`:

- **Cloud:** OpenAI, OpenRouter, Anthropic, Groq, DeepSeek, Mistral, Together AI, Fireworks AI.
- **Local:** Ollama (`http://localhost:11434/v1`), LM Studio (`http://localhost:1234/v1`), llama.cpp (`http://localhost:8080/v1`), vLLM (`http://localhost:8000/v1`).

## Configuration

1. Open **Settings → AI Providers**.
2. Toggle the top switch to **Enabled**.
3. Click **Add provider** and fill in:
   - **Name** — any label, e.g. `OpenRouter` or `Claude`.
   - **Protocol** — pick `OpenAI-compatible` or `Anthropic`. The
     quick-pick buttons below also set this for you.
   - **Base URL** — the API root, e.g.
     `https://openrouter.ai/api/v1` or `https://api.anthropic.com/v1`.
     Quick-pick buttons are provided for OpenRouter, OpenAI,
     Anthropic, and a local server.
   - **API Key** — paste the key. It is stored on this device's
     `data/config.json` and is masked (`***`) on read.
   - **Models** — type each model id and press Enter or click `+`
     (e.g. `openai/gpt-4o-mini`, `claude-3-5-sonnet-20241022`).
   - **Default model** — picked automatically once you add at least
     one model.
4. (Optional) Click **Test connection** to send a one-token smoke
   test and confirm credentials and connectivity.
5. Click **Save changes**.

If you configure more than one provider, mark one as the default
using the **Make default** button.

## Recommended models

These all work well with the FiestaBoard prompt format. Any current chat-completion model the provider exposes will work — these are just sensible defaults.

| Provider     | Protocol  | Model                                  | Notes                              |
| ------------ | --------- | -------------------------------------- | ---------------------------------- |
| OpenRouter   | OpenAI    | `openai/gpt-4o-mini`                   | Cheap, fast, reliable JSON output. |
| OpenRouter   | OpenAI    | `anthropic/claude-sonnet-4.6`          | High-quality, slower.              |
| OpenAI       | OpenAI    | `gpt-4o-mini`                          | Same as via OpenRouter.            |
| Anthropic    | Anthropic | `claude-sonnet-4-6`                    | Direct, no OpenRouter markup.      |
| Anthropic    | Anthropic | `claude-haiku-4-5-20251001`            | Cheaper, fast.                     |
| Local Ollama | OpenAI    | `qwen2.5:14b-instruct` or larger       | Needs a model that follows JSON.   |

> **Note:** Model IDs are versioned and providers periodically rotate them. This table is updated periodically, but the authoritative list of current Claude model IDs lives at [docs.anthropic.com](https://docs.anthropic.com/). If a suggested ID returns an "unknown model" error, check there for the current name.

The Anthropic protocol pins a stable `anthropic-version` header in `src/ai/protocols.py`, so any model ID Anthropic accepts on that version works — earlier IDs like `claude-3-5-sonnet-20241022` are still valid if you've configured them. Smaller (≤ 7B) local models often struggle to emit valid JSON for the FiestaBoard schema; if you see frequent "Could not parse JSON" errors, switch to a larger or instruction-tuned model.

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

- Two protocols supported: OpenAI-compatible chat completions, and
  the Anthropic Messages API. Other native APIs (Google Gemini,
  Cohere, …) can be reached today through OpenRouter, or added by
  registering a new entry in `src/ai/protocols.py`.
- No streaming UI: a single request/response.
- No automatic page creation or scheduling — you always review and
  click **Save**.
- No image/vision input.
- A modest per-process rate limit applies to `/pages/ai/generate` to
  protect against runaway clients (1 second between calls, 2
  concurrent).

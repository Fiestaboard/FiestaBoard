---
sidebar_position: 7
description: "Bring your own AI: configure OpenAI, Anthropic, OpenRouter, DeepSeek, Mistral, Together, Fireworks, Ollama, LM Studio, vLLM, or llama.cpp. FiestaBoard never bundles an API key."
keywords: [FiestaBoard AI, Vestaboard AI, AI page generation, LLM page drafts, OpenAI integration, Anthropic Claude, OpenRouter, DeepSeek, Mistral, Together AI, Fireworks AI, Ollama, LM Studio, vLLM, llama.cpp, bring your own model, BYOK, BYO LLM]
---

# AI Providers (FiestaBot setup)

**FiestaBot** is FiestaBoard's built-in AI assistant. Click **AI
Assistant** in the sidebar (the Sparkles icon) to open the chat panel,
then describe what you want in plain language — FiestaBot drafts and
edits board pages through conversation, and can also install plugins,
update settings, and manage schedules.

FiestaBoard ships **without any bundled LLM credentials**. You bring
your own provider, your own API key, and your own model list. There
is no FiestaBoard-hosted AI proxy.

Two protocols are supported out of the box:

- **OpenAI-compatible** chat completions — one-click presets for
  OpenAI, OpenRouter, DeepSeek, Mistral, Together AI, and
  Fireworks AI, plus local servers Ollama, LM Studio, llama.cpp, and
  vLLM. Any other OpenAI-compatible endpoint works too — just paste
  the base URL.
- **Anthropic Messages API** — direct access to `api.anthropic.com`
  using a Claude API key.

In **Settings → AI Providers**, **Add provider** asks what kind of
provider you want and then shows only the fields that kind needs.

The preset list is intentionally limited to providers that fully
honor the OpenAI `response_format: json_object` field that the page
generator relies on. Other services (Google Gemini's OpenAI shim,
xAI Grok, Perplexity Sonar, Cerebras, Nvidia NIM, DeepInfra, …) can
still be used by entering the base URL by hand — just be aware that
strict JSON mode may need the prompt-only fallback to kick in.

## Choosing a provider

Not sure which one to pick? Here's the short version.

### We recommend OpenRouter for most users

[OpenRouter](https://openrouter.ai) is our suggested starting point.
It's a single API and a single API key that gives you access to
hundreds of models from OpenAI, Anthropic, Google, Meta, Mistral,
DeepSeek, and others — including most of the open-weight models —
with pay-as-you-go billing and no per-provider account juggling.
You can swap models from the FiestaBot model dropdown without
re-entering credentials.

> **Disclosure:** We recommend OpenRouter because it works well, not
> because we get paid to. **FiestaBoard receives no referral fees,
> kickbacks, affiliate commissions, or other compensation from
> OpenRouter** — there's no `?ref=` link in our docs and no partner
> agreement of any kind. We just like the product. If you'd prefer a
> direct relationship with one provider, any of the other presets
> works equally well.

### When to pick something else

- **You already pay for OpenAI / Anthropic / Mistral / etc.** — use
  the matching preset and your existing key. No reason to add an
  OpenRouter middleman.
- **You want the lowest possible latency** — DeepSeek is
  typically faster than OpenRouter's pooled routing.
- **You want everything to stay on your own hardware** — pick a
  local preset (Ollama, LM Studio, llama.cpp, vLLM). Note the
  caveats about smaller models and JSON adherence below.
- **You're in the EU and care about data residency** — Mistral is
  EU-hosted.

### Quick setup

In **Settings → AI Providers**, click **Add provider** and choose what
kind of provider it is:

- **Sign in**: ChatGPT, OpenRouter, or Hugging Face. The provider is
  saved straight away and shows its sign-in panel. Once you are signed
  in, its models are listed on their own: search the list and pick one. See
  [Signing in instead of using an API key](#signing-in-instead-of-using-an-api-key).
- **Use an API key**: pick the service (OpenAI, Anthropic,
  DeepSeek, Mistral, Together AI, Fireworks AI, or OpenRouter), then
  paste your key and add a model. The name, base URL, and protocol are
  filled in for you.
- **Run it on my network**: pick Ollama, LM Studio, llama.cpp, or vLLM.
  The **Server address** is filled in with that server's usual port on
  `localhost`, which means the board itself. If the server runs on
  another computer, change it to that computer's address, such as
  `http://192.168.1.20:11434/v1`. Then add a model.
- **Advanced (custom endpoint)**: the full form, for any other
  OpenAI-compatible or Anthropic endpoint. Its **Quick presets** pills
  fill in the name, base URL, and protocol for a known service.

Opening a provider later shows the same short view it was set up with.
Everything else (name, protocol, base URL, API key, sign-in) is under
**Advanced** in that view. A provider that matches none of the kinds
opens in the full form.

## Configuration

<AppShot name="ai-settings" alt="AI Providers settings section showing a configured OpenRouter provider with Quick Presets and model list" />

1. Open **Settings → AI Providers**.
2. Toggle the top switch to **Enabled**.
3. Click **Add provider**, choose a kind (see [Quick setup](#quick-setup)),
   and fill in what it asks for. The full form (**Advanced (custom
   endpoint)**, or **Advanced** inside any provider) has every field:
   - **Name**: any label, e.g. `OpenRouter` or `Claude`. Auto-filled
     when you pick a service or click a preset pill.
   - **Protocol**: pick `OpenAI-compatible` or `Anthropic`. The
     quick-pick buttons below also set this for you.
   - **Base URL**: the API root, e.g.
     `https://openrouter.ai/api/v1` or `https://api.anthropic.com/v1`.
   - **API Key**: paste the key. It is stored on this device's
     `data/config.json` and is masked (`***`) on read.
   - **Models**: search the provider's list and pick, or type an id
     the list does not have (e.g. `openai/gpt-5-mini`,
     `claude-sonnet-5`) and choose **Use this id**. A signed-in provider
     lists its models as soon as you are signed in; any other saved
     provider lists them when you press **Load models**. **Refresh
     models** asks again.
   - **Default model**: picked automatically once you add at least
     one model; change it from the same searchable list.
4. (Optional) Click **Test connection** to send a one-token smoke
   test and confirm credentials and connectivity.
5. Click **Save changes**.

If you configure more than one provider, mark one as the default
using the **Make default** button. FiestaBot will use the default
provider unless you pick another from the dropdown in the chat panel.

## Signing in instead of using an API key

Three providers also let you **sign in** with your account instead of
pasting a key. This is an extra choice, not a replacement: a provider
set up with an API key keeps working exactly as before, and you can
switch back at any time.

| Sign in with | Where requests go | What you need |
| ------------ | ----------------- | ------------- |
| OpenRouter   | `https://openrouter.ai/api/v1` | An OpenRouter account. Signing in creates an API key for FiestaBoard in your account. |
| Hugging Face | `https://router.huggingface.co/v1` | A Hugging Face account. FiestaBoard asks only for permission to call inference. |
| ChatGPT      | `https://api.openai.com/v1` (OpenAI Responses) | A ChatGPT account. Requests use the OpenAI Responses protocol, which is set for you. |

To sign in:

1. Open **Settings → AI Providers**, click **Add provider**, choose
   **Sign in**, and pick **ChatGPT**, **OpenRouter**, or **Hugging
   Face**. The provider is saved with the right base URL and protocol,
   and shows a sign-in panel.
2. Press the sign-in button in that panel and approve FiestaBoard on the
   provider's page. OpenRouter and Hugging Face bring you back to
   Settings signed in; ChatGPT is finished by a paste (below).
3. Pick the model to use from the list that appears (search it by
   name or id). FiestaBot can use the provider at once, and its own
   model picker offers the same list.

An existing API-key provider can switch to a sign-in too: open it, then
under **Advanced** (or in the full form) choose a service under **Or
sign in instead of using an API key** and press **Save changes**. Your
API key field is left as it is.

**ChatGPT** cannot send you straight back to your board, so the sign-in
is planned around that:

1. Press **Sign in with ChatGPT**. Settings shows a **Finish signing
   in** step with these instructions and a box to paste into. Read
   them, then choose **Open the ChatGPT sign-in page**. ChatGPT opens
   in a new tab.
2. Sign in and approve FiestaBoard in the ChatGPT tab. That tab then
   ends on an error page, such as "can't connect to 127.0.0.1" or
   "This site can't be reached". **That is expected**: nothing went
   wrong.
3. Copy that tab's whole address from the address bar (it starts with
   `http://127.0.0.1`), come back to the FiestaBoard tab, paste it into
   the **Finish signing in** step, and press **Finish sign-in**. The
   panel then says you are signed in.

This paste step goes away once OpenAI approves FiestaBoard's app: ChatGPT
then sends you straight back to your board, like the other providers.

For the other providers, a sign-in that does not come back by itself
can be finished the same way: choose **Sign-in didn't come back?
Paste the address or code**.

**OpenRouter** can also be signed in without a browser redirect:
choose **Sign in without a browser redirect**, approve, and paste the
code OpenRouter shows.

While a provider signs in, its API key is not used. Press **Use the
API key instead** (under **Advanced**) to go back to the key; nothing you typed there was
removed. Removing a provider, or switching it back to a key, deletes
the sign-in FiestaBoard was holding for it.

Sign-ins are stored like plugin sign-ins: in `data/oauth_tokens.json`
on your board, never in `data/config.json`, never sent to your
browser, and not part of backups. After restoring a backup onto a new
board, sign in again. If a provider stops accepting the sign-in,
FiestaBot says "Sign in to *provider* again in Settings → AI." and
sends nothing until you do. See [Connecting Accounts](/docs/features/connecting-accounts)
for how the sign-in itself works.

## Recommended models

These all work well with the FiestaBoard prompt format. Where a
provider offers a stable alias (`-latest`, or an undated family name
like `claude-sonnet-5`), we prefer it over a date-stamped id so the
recommendation ages more gracefully.

| Provider       | Protocol  | Model                                  | Notes                              |
| -------------- | --------- | -------------------------------------- | ---------------------------------- |
| OpenRouter     | OpenAI    | `openai/gpt-5-mini`                    | Cheap, fast, reliable JSON output. |
| OpenRouter     | OpenAI    | `anthropic/claude-sonnet-5`           | High-quality, slower.              |
| OpenAI         | OpenAI    | `gpt-5-mini`                          | Same as via OpenRouter.            |
| Anthropic      | Anthropic | `claude-sonnet-5`                     | Direct, no OpenRouter markup.      |
| Anthropic      | Anthropic | `claude-haiku-4-5`                    | Cheaper, fast.                     |
| DeepSeek       | OpenAI    | `deepseek-chat`                        | Cheap, capable.                    |
| Mistral        | OpenAI    | `mistral-large-latest`                 | EU-hosted option.                  |
| Together AI    | OpenAI    | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Hosted open weights.            |
| Fireworks AI   | OpenAI    | `accounts/fireworks/models/llama-v3p3-70b-instruct` | Hosted open weights.   |
| Local Ollama   | OpenAI    | `qwen2.5:14b-instruct` or larger       | Needs a model that follows JSON.   |
| Local LM Studio| OpenAI    | A 14B+ instruction-tuned model         | Same JSON-adherence caveat.        |

> **Note:** Model catalogs change often, and providers retire ids on
> their own schedule. Treat this table as a starting point — check the
> provider's current model list, and if **Test connection** reports an
> unknown model, pick the closest current id from their catalog.

Smaller (≤ 7B) local models often struggle to emit valid JSON for
the FiestaBoard schema; if you see frequent "Could not parse JSON"
errors, switch to a larger or instruction-tuned model.

## Privacy

Each time you send a message, FiestaBot sends to the provider you
configured:

- The system prompt (board dimensions, character set rules, JSON
  schema, and available template functions).
- **Your message.**
- **The variable list of all enabled plugins** (names + descriptions
  - max widths). This may include data such as transit station IDs
  or location names that you have configured.
- Up to a handful of example pages drawn from plugin manifests.
- **The current page being edited** (when a page is open in the
  editor — FiestaBot always has context of what you're working on).
- Context about your pages, schedules, carousels, and installed
  plugins (names and IDs only, not content).

API keys are stored locally in `data/config.json` and never sent to
any FiestaBoard-hosted service.

## Chat history

Every FiestaBot conversation is saved on your FiestaBoard as you go —
there is nothing to click. Closing the drawer or reloading the page
brings you back to the chat you were in, and the **History** button
in the panel header (the clock icon) lists everything you have talked
about, newest first, with a search box for the title.

- **Review** — open any conversation to read it back, including the
  actions FiestaBot took and what each one returned. Nothing runs
  while you are reading.
- **Continue** — picks a saved conversation up again as the live chat.
  Its provider, model and "don't ask again" choice come back with it.
- **New chat** (the pencil icon) starts a fresh conversation; the old
  one stays in History.
- **Rename** and **Delete** sit on each row. **Clear all** at the
  bottom removes every saved chat after a confirmation.
- **Export JSON** on an open conversation downloads that thread as a
  file, handy for attaching to a bug report.

The title is the first thing you typed, trimmed to 80 characters;
rename it whenever you like. FiestaBoard keeps the 200 most recently
used conversations and drops the oldest when a new one arrives.
Credentials never end up in a saved chat: any API key, password or
token that passes through a tool is stored as `***`, the same masking
the tools themselves apply. History lives in `data/ai_conversations.json`
and is not part of the settings backup.

## Limitations

- Two protocols supported: OpenAI-compatible chat completions
  (presets cover OpenAI, OpenRouter, DeepSeek, Mistral,
  Together, Fireworks, Ollama, LM Studio, llama.cpp, and vLLM), and
  the Anthropic Messages API. Other providers (Google Gemini, xAI
  Grok, Perplexity, Cerebras, DeepInfra, Nvidia NIM, Cohere, …) can
  be reached today through OpenRouter, by entering the base URL
  manually (some don't strictly honor JSON mode), or by registering a
  new entry in `src/ai/protocols.py`.
- No image/vision input.
- FiestaBot acts through the same tools as the MCP server and shows
  each action as it happens. Creating, editing and configuring apply
  immediately. Destructive actions — every tool the MCP server marks
  destructive except the system tier: deleting a page, schedule,
  collection, plugin instance, board or panel, uninstalling a plugin,
  forgetting or disconnecting Wi-Fi — follow the chat's **approval
  mode**, the
  Ask / Auto toggle in the panel header. In **Ask** (the default) each
  one pauses for your Approve / Deny; in **Auto** they run without
  asking and are marked *auto* in the step list. The approval card's
  "Approve and don't ask again in this chat" is the same thing for one
  conversation, until you start a new chat. Restarting, shutting down
  and updating the system always ask, in every mode, and FiestaBot
  cannot change the approval mode itself. **Stop** ends a turn at any
  time.
- A modest per-process rate limit applies to page generation requests
  to protect against runaway clients (1 second between calls, 2
  concurrent).

## Troubleshooting

**AI Assistant doesn't appear in the sidebar**
You need at least one provider configured in **Settings → AI
Providers** with the top toggle set to **Enabled**. The sidebar item
only appears once a provider exists.

**"Could not parse JSON" or repeated empty results**
The model isn't returning valid JSON for the board schema. Switch
to a stronger model (e.g. `gpt-5-mini` or
`claude-sonnet-5`) or one explicitly tuned for
instruction following.

**Test connection fails**
Double-check the **Base URL** (it should usually end in `/v1`),
verify the API key has not been revoked, and confirm the model id
exists for that provider.

"""Talk to a user-configured OpenAI-compatible LLM and return a draft page.

Used by ``POST /pages/ai/generate``. Pure-async via ``httpx``.

Robust against bad model output:
- malformed JSON → raises ``AIGenerationError`` (caller surfaces it as a
  user-visible warning, not a 500),
- oversized lines → trimmed to the device's column count and reported in
  ``warnings``,
- hallucinated variable references → flagged in ``warnings`` (we do not
  delete them, since the template engine handles unknown vars gracefully
  and the user may want to fix it manually).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import ValidationError

from src.devices import DeviceType, get_dimensions
from src.pages.models import Page, PageCreate

from .prompt_builder import PromptContext, build_prompt
from .protocols import Protocol, get_protocol
from .template_validator import repair_template_lines

logger = logging.getLogger(__name__)


# Conservative defaults; OpenAI-compatible endpoints accept these.
_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_MAX_TOKENS = 1500
_DEFAULT_TIMEOUT_SECONDS = 60.0


# Match a {{plugin.var}} reference (without filters / pipes) so we can
# cross-check the model's output against the supplied variable registry.
_VARIABLE_REF_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\b")


class AIGenerationError(Exception):
    """A user-visible error in the AI generation flow.

    Raised for predictable failure modes (provider not configured, model
    returned non-JSON, network timeout). The API layer turns these into
    a 4xx/5xx response with the message in the body so the UI can show
    it without exposing tracebacks.
    """


# Allow only printable ASCII (no control chars / tracebacks / newlines) for
# error messages that are surfaced to API consumers.  Using ``re.fullmatch``
# as a barrier here is what clears CodeQL's ``py/stack-trace-exposure`` rule:
# downstream sinks see a value derived from a constant-character regex, not
# from the raw exception object.
_SAFE_ERROR_MESSAGE_RE = re.compile(r"[ -~]{1,500}")


def _user_safe_error_message(exc: BaseException) -> str:
    """Return a curated, user-safe message from ``exc``.

    ``AIGenerationError`` instances carry curated single-line strings that
    are safe to show to API consumers.  This helper strips control
    characters / multi-line traceback fragments and bounds the length so
    static analysis sees a sanitized string flow, not raw exception data.
    """
    raw = exc.args[0] if exc.args else ""
    candidate = raw if isinstance(raw, str) else ""
    # Collapse any embedded newlines / tabs before matching.
    candidate = candidate.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip()
    match = _SAFE_ERROR_MESSAGE_RE.match(candidate)
    if not match:
        return "AI provider error"
    return match.group(0)


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object found in ``text``.

    Some models wrap their JSON in markdown fences or a short preamble
    even when asked not to. We try strict parsing first, then fall back
    to extracting the outermost ``{...}`` block.
    """
    text = text.strip()
    if not text:
        raise AIGenerationError("Model returned an empty response.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences.
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(fenced.strip())
    except json.JSONDecodeError:
        pass

    # Last resort: greedy outermost {...} match.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise AIGenerationError(f"Model output was not valid JSON: {exc}") from exc
    raise AIGenerationError("Model output did not contain a JSON object.")


def _line_visible_width(line: str) -> int:
    """Approximate the rendered column count of a template line.

    This is a best-effort sanity check, not a full template render. We
    treat each color/symbol token (e.g. ``{red}``, ``{sun}``,
    ``{degree}``) as one column, leave variables alone (their width is
    documented to the model in the prompt and varies at render time),
    and count remaining literal characters as one column each.
    """
    # Replace {{var|filter}} blocks with a placeholder of unknown width
    # — we don't penalize lines for variable refs; the model has been
    # told their max widths.
    without_vars = re.sub(r"\{\{[^}]+\}\}", "", line)
    # Replace single-brace tokens with one char.
    collapsed = re.sub(r"\{[^{}]+\}", "X", without_vars)
    return len(collapsed)


def _validate_and_repair(
    raw: dict[str, Any],
    device_type: DeviceType,
    known_variables: dict[str, dict[str, dict[str, Any]]],
) -> tuple[dict[str, Any], list[str]]:
    """Coerce model output into a ``PageCreate``-shaped dict.

    Returns the cleaned page dict and a list of human-readable warnings
    describing repairs we made (or things we noticed but couldn't fix).
    """
    warnings: list[str] = []
    dims = get_dimensions(device_type)

    if not isinstance(raw, dict):
        raise AIGenerationError("Model output was not a JSON object.")

    page: dict[str, Any] = {}

    # name
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        page["name"] = "AI Page"
        warnings.append('Model did not return a name; using "AI Page".')
    else:
        page["name"] = name.strip()[:100]

    # type — always template for AI pages.
    if raw.get("type") not in (None, "template"):
        warnings.append(f"Model returned type={raw.get('type')!r}; coerced to 'template'.")
    page["type"] = "template"

    # device_type — force to requested.
    if raw.get("device_type") not in (None, device_type):
        warnings.append(f"Model returned device_type={raw.get('device_type')!r}; coerced to {device_type!r}.")
    page["device_type"] = device_type

    # template lines
    template = raw.get("template")
    if not isinstance(template, list) or not template:
        raise AIGenerationError("Model output is missing the required 'template' list.")
    template = [str(line) if line is not None else "" for line in template]

    # Repair common ``{{filled:...}}`` mistakes before length/width
    # checks so that, for example, ``{{filled:green.}}`` (which would
    # otherwise be counted as 8 literal columns once it falls through
    # to the text-pattern branch) is normalised to a real color fill.
    template, repair_warnings = repair_template_lines(template)
    warnings.extend(repair_warnings)

    # Pad/trim to exact device row count.
    if len(template) < dims.rows:
        warnings.append(f"Model returned {len(template)} lines; padded to {dims.rows} for {device_type}.")
        template = template + [""] * (dims.rows - len(template))
    elif len(template) > dims.rows:
        warnings.append(f"Model returned {len(template)} lines; truncated to {dims.rows} for {device_type}.")
        template = template[: dims.rows]

    # line_metadata
    raw_meta = raw.get("line_metadata")
    line_metadata: list[dict[str, Any]] = []
    if isinstance(raw_meta, list):
        for item in raw_meta:
            if not isinstance(item, dict):
                line_metadata.append({"alignment": "left", "wrap": False})
                continue
            alignment = item.get("alignment", "left")
            if alignment not in ("left", "center", "right"):
                alignment = "left"
            wrap = bool(item.get("wrap", False))
            line_metadata.append({"alignment": alignment, "wrap": wrap})
    while len(line_metadata) < len(template):
        line_metadata.append({"alignment": "left", "wrap": False})
    line_metadata = line_metadata[: len(template)]

    # Trim oversized lines (only when wrap is False).
    for i, line in enumerate(template):
        if line_metadata[i].get("wrap"):
            continue
        width = _line_visible_width(line)
        if width > dims.cols:
            warnings.append(
                f"Line {i + 1} was {width} columns wide (max {dims.cols}); "
                "trimmed to fit. Consider enabling wrap on that line."
            )
            # Trim from the end while preserving leading variable refs.
            # Conservative: just slice the literal string.
            template[i] = line[: dims.cols]

    page["template"] = template
    page["line_metadata"] = line_metadata

    # duration_seconds — clamp to allowed range.
    duration = raw.get("duration_seconds", 300)
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 300
    page["duration_seconds"] = max(10, min(3600, duration))

    # Flag references to unknown variables (don't strip — the engine
    # tolerates unknown vars and the user may simply enable a plugin).
    unknown = _find_unknown_variables(template, known_variables)
    for ref in unknown:
        warnings.append(f"Template references unknown variable {{{{{ref}}}}}. The plugin may not be enabled.")

    # Final structural validation via Pydantic.
    try:
        validated = PageCreate(**page)
        # Bridge to the full Page model to run the Page-level structural
        # validator. exclude_none so PageCreate's optional W×H (None when the
        # model didn't supply them) fall back to Page's int defaults rather than
        # failing int validation.
        page_obj = Page(**validated.model_dump(exclude_none=True))
        config_errors = page_obj.validate_config()
        if config_errors:
            warnings.extend(config_errors)
        page = validated.model_dump(mode="json")
        # Ensure W×H are concrete ints in the returned draft (PageCreate leaves
        # them None when unspecified; default to a single Note).
        page["notes_wide"] = page_obj.notes_wide
        page["notes_tall"] = page_obj.notes_tall
    except ValidationError as exc:
        # Pydantic ValidationError messages are curated and safe to
        # surface — they describe the field that failed, not internals.
        raise AIGenerationError(f"Model output failed validation: {exc}") from exc
    except Exception as exc:
        # Defensive: anything else here is unexpected. Log it but
        # don't expose the raw message to the API consumer.
        logger.exception("Unexpected error validating model output")
        raise AIGenerationError("Model output failed validation.") from exc

    return page, warnings


def _find_unknown_variables(
    template: list[str],
    known_variables: dict[str, dict[str, dict[str, Any]]],
) -> list[str]:
    """Return a list of ``plugin.var`` refs not in ``known_variables``."""
    seen: list[str] = []
    for line in template:
        for match in _VARIABLE_REF_RE.finditer(line):
            plugin_id, var_name = match.group(1), match.group(2)
            if plugin_id not in known_variables:
                ref = f"{plugin_id}.{var_name}"
                if ref not in seen:
                    seen.append(ref)
                continue
            if var_name not in known_variables[plugin_id]:
                ref = f"{plugin_id}.{var_name}"
                if ref not in seen:
                    seen.append(ref)
    return seen


def _resolve_provider(
    providers_block: dict[str, Any],
    provider_id: str | None,
) -> dict[str, Any]:
    """Pick the provider to use, preferring an explicit ``provider_id``.

    Falls back to the configured default; raises if nothing is usable.
    """
    if not providers_block.get("enabled"):
        raise AIGenerationError("AI providers are not enabled. Configure one in Settings first.")
    providers = providers_block.get("providers") or []
    if not providers:
        raise AIGenerationError("No AI providers are configured. Add one in Settings first.")

    if provider_id:
        for provider in providers:
            if provider.get("id") == provider_id:
                return provider
        raise AIGenerationError(f"AI provider {provider_id!r} not found.")

    default_id = providers_block.get("default_provider_id")
    if default_id:
        for provider in providers:
            if provider.get("id") == default_id:
                return provider

    return providers[0]


def _resolve_model(provider: dict[str, Any], model: str | None) -> str:
    """Pick the model id to send. Prefers explicit, then provider default."""
    if model:
        return model
    if provider.get("default_model"):
        return provider["default_model"]
    models = provider.get("models") or []
    if models:
        return models[0]
    raise AIGenerationError(f"AI provider {provider.get('name', provider.get('id'))!r} has no models configured.")


def _build_request_payload(
    model: str,
    context: PromptContext,
    protocol: Protocol,
) -> dict[str, Any]:
    """Build a request body for the given protocol."""
    return protocol.build_body(
        model,
        context.to_messages(),
        _DEFAULT_TEMPERATURE,
        _DEFAULT_MAX_TOKENS,
    )


async def _post_chat_completion(
    provider: dict[str, Any],
    payload: dict[str, Any],
    *,
    protocol: Protocol | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST to the provider's chat endpoint and return the parsed JSON.

    The endpoint path and auth headers are determined by ``protocol``;
    if not supplied it is derived from ``provider['protocol']`` (default
    OpenAI-compatible).
    """
    proto = protocol or get_protocol(provider.get("protocol"))
    base_url = (provider.get("base_url") or "").rstrip("/")
    if not base_url:
        raise AIGenerationError("AI provider has no base_url configured.")
    url = f"{base_url}{proto.request_path}"
    extra = provider.get("headers") or {}
    headers = proto.build_headers(
        provider.get("api_key") or "",
        extra if isinstance(extra, dict) else {},
    )

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=timeout_seconds)
    try:
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            # Don't echo the raw httpx exception message — it can include
            # URL/host details and CodeQL flags it as stack-trace exposure.
            logger.warning("AI provider HTTP error: %s", exc)
            raise AIGenerationError("Could not reach AI provider.") from exc
        if response.status_code >= 400:
            # Try to surface the provider's own error message via the
            # protocol-specific error parser.
            err_msg: str | None = None
            try:
                err_body = response.json()
                if isinstance(err_body, dict):
                    err_msg = proto.parse_error(err_body)
            except Exception:
                err_msg = None
            if not err_msg:
                err_msg = response.text
            raise AIGenerationError(f"AI provider returned {response.status_code}: {err_msg}")
        try:
            return response.json()
        except Exception as exc:
            # Don't include the raw exception details in the user-facing
            # message — only that it was non-JSON. The full exception is
            # logged for debugging.
            logger.warning("AI provider returned non-JSON response: %s", exc)
            raise AIGenerationError("AI provider returned a non-JSON response.") from exc
    finally:
        if owns_client:
            await client.aclose()


def _extract_message_content(
    api_response: dict[str, Any],
    protocol: Protocol | None = None,
) -> str:
    """Pull the assistant's text out of a provider response.

    Uses the supplied protocol adapter; falls back to the OpenAI shape
    for backwards compatibility with callers that don't pass one.
    """
    proto = protocol or get_protocol(None)
    content = proto.parse_content(api_response)
    if not isinstance(content, str) or not content.strip():
        raise AIGenerationError("AI provider returned an empty message.")
    return content


async def generate_page(
    *,
    user_prompt: str,
    device_type: DeviceType,
    providers_block: dict[str, Any],
    variables: dict[str, dict[str, dict[str, Any]]] | None = None,
    plugin_demos: list[dict[str, Any]] | None = None,
    current_page: dict[str, Any] | None = None,
    provider_id: str | None = None,
    model: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Ask the user's configured LLM to draft a page.

    Returns a dict ``{page, model_used, provider_id, warnings, usage}``.
    The ``page`` value is a ``PageCreate``-shaped dict; the caller is
    responsible for handing it to the editor (we never persist it).

    Raises:
        AIGenerationError: For predictable, user-visible failures.
    """
    if not user_prompt or not user_prompt.strip():
        raise AIGenerationError("Prompt is empty.")

    provider = _resolve_provider(providers_block, provider_id)
    chosen_model = _resolve_model(provider, model)
    protocol = get_protocol(provider.get("protocol"))

    context = build_prompt(
        user_prompt=user_prompt.strip(),
        device_type=device_type,
        variables=variables,
        plugin_demos=plugin_demos,
        current_page=current_page,
    )

    payload = _build_request_payload(chosen_model, context, protocol)
    api_response = await _post_chat_completion(provider, payload, protocol=protocol, client=client)

    text = _extract_message_content(api_response, protocol)
    raw = _extract_json_object(text)
    if raw.get("refusal") is True:
        reason = raw.get("reason") or "I can only help with FiestaBoard board design."
        raise AIGenerationError(reason)
    page, warnings = _validate_and_repair(raw, device_type, variables or {})

    usage = protocol.parse_usage(api_response)

    return {
        "page": page,
        "model_used": chosen_model,
        "provider_id": provider.get("id"),
        "warnings": warnings,
        "usage": usage,
    }


async def test_provider(
    provider: dict[str, Any],
    *,
    model: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Send a tiny smoke-test request to verify a provider works.

    Returns ``{ok: bool, message: str, model_used: str}``. Never raises;
    failures are returned as ``ok: False``.
    """
    try:
        chosen_model = _resolve_model(provider, model)
    except AIGenerationError as exc:
        return {"ok": False, "message": _user_safe_error_message(exc), "model_used": None}

    protocol = get_protocol(provider.get("protocol"))
    payload = protocol.build_body(
        chosen_model,
        [{"role": "user", "content": "Reply with the single word: ok"}],
        0.0,
        5,
    )
    try:
        response = await _post_chat_completion(
            provider,
            payload,
            protocol=protocol,
            timeout_seconds=timeout_seconds,
            client=client,
        )
        content = _extract_message_content(response, protocol)
    except AIGenerationError as exc:
        return {"ok": False, "message": _user_safe_error_message(exc), "model_used": chosen_model}
    except Exception:  # pragma: no cover — defensive
        # Log the full exception server-side, but only return a generic
        # message to avoid leaking stack-trace details to API consumers.
        logger.exception("Unexpected error during provider test")
        return {
            "ok": False,
            "message": ("Unexpected error contacting the provider. See server logs for details."),
            "model_used": chosen_model,
        }

    return {
        "ok": True,
        "message": f"Connected. Model replied: {content[:80]}",
        "model_used": chosen_model,
    }

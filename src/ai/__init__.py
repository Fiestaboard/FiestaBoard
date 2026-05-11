"""AI-assisted page generation for the FiestaBoard page editor.

Implements the "Gen AI" feature: users supply a natural-language prompt
in the page editor and a user-configured, OpenAI-compatible LLM returns
a draft page (template + per-line metadata) that is loaded into the
editor for review.

This package is BYO-LLM: users supply their own endpoint, key, and list
of model identifiers. FiestaBoard never bundles a key.
"""

from .prompt_builder import build_prompt, PromptContext
from .generator import generate_page, AIGenerationError

__all__ = [
    "build_prompt",
    "PromptContext",
    "generate_page",
    "AIGenerationError",
]

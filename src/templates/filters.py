"""The template filter roster — one table, owned by the code that runs them.

``{{var|upper|truncate:6}}``. :meth:`src.templates.engine.TemplateEngine._apply_filter`
implements these; ``validate_template`` rejects anything else; the editor's
``GET /templates/variables`` advertises them; and the AI teaching text
(:mod:`src.ops.teaching`) re-exports this table so the MCP instructions and the
chat prompt describe the same set.

Three copies of this list had already drifted apart: the engine's module
docstring promised ``|upper``/``|lower`` that were never implemented, the
teaching text denied they existed, and the ``/templates/variables`` literal
omitted the real ``zeropad:N``.

It lives here rather than in ``src.ops.teaching`` because a filter is engine
behavior, and because importing ``src.ops`` runs its package ``__init__``, which
pulls in the whole operation layer — the engine must not reach up into that
(``tests/test_tail_routers_decoupled.py``).
"""

from __future__ import annotations

#: (spelling as written in a template, one-line teaching summary).
#: ``tests/test_ops_teaching.py`` runs every entry through the engine, so a
#: filter cannot be advertised without working.
TEMPLATE_FILTERS: tuple[tuple[str, str], ...] = (
    ("upper", "uppercase the value"),
    ("lower", "lowercase the value"),
    ("pad:N", "right-pad the value with spaces to N chars"),
    ("truncate:N", "cut the value to N chars"),
    ("zeropad:N", "left-pad the value with zeros to N chars"),
    ("wrap", "let a long value flow into the empty lines below"),
)

#: Filter names the engine accepts, for validation. Derived from the roster so a
#: filter cannot be implemented, taught, and still reported as unknown.
FILTER_NAMES: frozenset[str] = frozenset(spelling.split(":")[0] for spelling, _summary in TEMPLATE_FILTERS)

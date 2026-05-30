"""Collection module for grouping pages and selecting which one to display.

A Collection is an ordered set of pages plus a *selection mode* that decides
which page is active at any given moment. The first two modes are:

- ``time``: deterministic time-sliced rotation (the classic "carousel").
- ``variable``: walk an ordered list of (expression, page_id) rules and pick
  the first whose expression evaluates truthy against the current template
  context, falling back to ``default_page_id``.

Collections can be referenced anywhere a page_id is accepted via the prefixed
ID format: ``collection:{uuid}``.
"""

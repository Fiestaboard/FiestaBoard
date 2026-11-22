---
"fiestaboard": patch
---

The page editor's preview marks where a too-long line is cut, says which integrations are switched off when a page shows ??? for them (with a link to Integrations), and Sample mode now fills in a switched-off integration's example values. `GET /v1/variables` lists installed-but-off integrations with their examples in a new `disabled_plugins` field. A line with `{{fill_space}}` (or another fill) is no longer reported as too long: a fill only takes the room the rest of the row leaves.

---
title: Private settings projections
description: Keep configuration responses and assistant exports consistent with stored private fields.
---

# Private settings projections

Keep custom provider header values private in settings responses and assistant exports. Restore echoed values from the same stored provider/header during edits; reject unresolved values before changing settings. Preserve explicit removals and replacements.

Use the existing schema projection for plugin settings in assistant backups, resolving named instances through their base manifest and withholding unavailable configurations. Project the backup snapshot itself. Preserve ordinary downloadable backups for restore.

Add failing regression cases first, then run the focused configuration, settings, backup and MCP suites, Python lint and format checks, and the full Python suite. No UI layout or asset changes are needed.

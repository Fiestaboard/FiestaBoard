# Three release channels

Owner request: expose Stable, Beta and Alpha preview with published versions in Settings → System. The owner selected `three_channel_everywhere` (Jev p=0.59).

1. Add backend regression tests for isolated discovery, running-channel reporting, major-upgrade confirmation and fail-closed backups.
2. Extend the existing channel endpoints and snapshot/leave service; preserve both the original Stable recovery snapshot and the pre-Alpha snapshot. Jev chose preserving the original recovery snapshot over replacing it, p=0.98.
3. Replace the opt-in card with FiestaUI's accessible ChoiceCardGroup and ChoiceCard primitives. Show each version and a one-line description; confirm before any request and explain migration, backups and downgrade data loss. Home Assistant retains its supervisor explanation.
4. Add chooser-state unit coverage and one Playwright flow, including keyboard interaction and axe. Pin the registry FiestaUI alpha.2 version required by ChoiceCard.
5. Run full Python and web suites, static checks, build, layout and accessibility gates in isolated `cx-` Docker resources. Publish an unmerged PR into `alpha`, obtain independent Astra review and record observed results.

Stable never discovers prereleases; Beta never discovers the v11 preview. Alpha pulls only `v11-alpha`; the lane's publishing workflow is unchanged.

## Port to `main` (Stable line)

`main` pins the released FiestaUI 8.16.0, which has no `ChoiceCardGroup`/`ChoiceCard` (they first ship in the 8.17 prerelease line). The Stable-line port keeps 8.16.0 and renders the same chooser with FiestaUI's `ToggleCardGroup`/`ToggleCard` radiogroup instead; behaviour, copy, endpoints and backups are identical to the `alpha` change. The kit is not upgraded on `main`. Jev chose this over blocking the port or pinning a prerelease kit on Stable, p=0.98. Its single `minor` changeset follows `main`'s release conventions (no pre mode).

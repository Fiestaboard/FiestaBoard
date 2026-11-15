# Three release channels

Owner: OWNER-ACTIONS 2026-11-15, three_channel_everywhere.

1. Test discovery isolation and explicit confirm plus fail-closed backup on major upgrades.
2. Add Alpha preview -> v11-alpha without changing latest/beta publishers.
3. Replace the Settings System opt-in with FiestaUI ChoiceCardGroup, versions/current markers and confirmation risk explanation. Keep Home Assistant explanation.
4. Re-enable v11 switching and constrain Update Now to v11-alpha.
5. Run Python, UI coverage/static/build and isolated one-worker browser/axe checks; review each PR independently and leave unmerged.

Chooser decision: Jev radio_group p=0.83 (confidence 0.79). Source verification found ChoiceCardGroup is the exported FiestaUI radio group (no RadioGroup export); use it with optional media omitted.

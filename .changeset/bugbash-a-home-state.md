---
"fiestaboard": patch
---

Home, Compose and Change Page agree with the board: the preview catches up within seconds of Show now, the "Until <next Schedule change>" chip stays offered while an Override runs, display detail names the Override's page, Up next lists up to three changes, a Schedule gap reads in plain words, and the display switcher marks a display that needs a look. `GET /v1/boards/{board}` adds `schedule_next_change_at`, `schedule_next_page_id`, `upcoming_changes` and `override_page_id`.

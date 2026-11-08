---
"fiestaboard": patch
---

MQTT's `current_page` sensor now reports the page the board is actually showing (including scheduled, collection, override and silence pages) and publishes as soon as the page changes, instead of reporting the manually selected page.

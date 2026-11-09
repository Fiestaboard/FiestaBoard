---
"fiestaboard": minor
---

Copy a page for another display at that display's size, with a report of what was cut, and organize pages with tags you can filter the library by. Tags can include emoji, joined ones too. In the API, pages gain an optional `tags` list (on `/v1` as well); a request whose `tags` isn't a list of tags is now rejected.

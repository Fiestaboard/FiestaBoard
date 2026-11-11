---
"fiestaboard": patch
---

Docker Compose no longer fails with "env file .env not found" on a fresh install: the `.env` file is now optional, and an unset `FIESTAUPDATER_TOKEN` no longer prints a warning.

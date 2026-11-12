---
"fiestaboard": patch
---

FiestaBot now always asks before installing or updating plugins, restarting or updating FiestaBoard, changing its update channel, update schedule or TV kiosk, or changing where a stored key is sent (an AI provider, a board's address or the MQTT broker), whatever the approval mode. It only runs an approved action that it actually paused on, and it leaves installing from a Git URL to the Integrations page. With sign-in turned off, a configured API token now also protects the AI chat.

"""Saved FiestaBot conversations (#2022).

The chat panel keeps the live transcript in memory and replays it to
``POST /pages/ai/chat`` on every turn; this package is where that
transcript is *kept*. The panel autosaves it under a client-generated id
(``PUT /ai/conversations/{id}``), lists past chats, reopens one to review
it, and resumes it as the live transcript again.

This is the app's own chat loop only. External MCP clients keep their own
history, and none of the MCP tools can read or write this store.
"""

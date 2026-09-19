"""``/ai/conversations`` — saved FiestaBot chats (#2022).

The store is the client's autosave target: the panel PUTs its whole
transcript under a client-generated id after every turn, and reads it back
to review or resume. These tests drive the routes through the real app and
the real store in the isolated data dir; nothing inside the process is
mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.paths import get_data_dir

CONV_A = "11111111-1111-4111-8111-111111111111"
CONV_B = "22222222-2222-4222-8222-222222222222"
MISSING = "00000000-dead-beef-0000-000000000000"


def _transcript(first_line: str = "Build a weather page") -> list[dict]:
    return [
        {"role": "user", "content": first_line},
        {
            "role": "assistant",
            "content": "Done.",
            "toolCalls": [
                {
                    "id": "tc1",
                    "name": "create_page",
                    "args": {"name": "Weather", "template_lines": ["SUNNY"]},
                    "phase": "ok",
                    "result": {"id": "tc1", "name": "create_page", "status": "ok", "result": {"page_id": "p1"}},
                }
            ],
        },
    ]


def _body(**overrides) -> dict:
    body = {
        "provider_id": "p1",
        "model": "test-model",
        "approval": False,
        "messages": _transcript(),
    }
    body.update(overrides)
    return body


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _store_path() -> Path:
    return get_data_dir() / "ai_conversations.json"


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def test_put_creates_a_conversation_under_the_client_id_with_201(client):
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == CONV_A
    assert body["provider_id"] == "p1"
    assert body["model"] == "test-model"
    assert body["approval"] is False
    assert body["messages"] == _transcript()
    assert body["created_at"].endswith("+00:00")
    assert body["updated_at"] == body["created_at"]


def test_put_derives_the_title_from_the_first_user_line(client):
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body())
    assert response.json()["title"] == "Build a weather page"


def test_put_truncates_a_derived_title_to_80_characters(client):
    long_line = "x" * 200
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=_transcript(long_line)))
    assert response.json()["title"] == "x" * 80


def test_put_again_updates_in_place_with_200_and_keeps_created_at(client):
    created = client.put(f"/ai/conversations/{CONV_A}", json=_body()).json()
    messages = [*_transcript(), {"role": "user", "content": "And a clock"}]
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=messages))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_at"] == created["created_at"]
    assert body["updated_at"] >= created["updated_at"]
    assert len(body["messages"]) == 3
    assert client.get("/ai/conversations").json()["total"] == 1


def test_put_keeps_a_renamed_title_across_autosaves(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    client.patch(f"/ai/conversations/{CONV_A}", json={"title": "Morning board"})
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body())
    assert response.json()["title"] == "Morning board"


def test_put_rejects_an_empty_transcript_with_422(client):
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=[]))
    assert response.status_code == 422


def test_put_rejects_a_message_with_an_unknown_role_with_422(client):
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=[{"role": "robot", "content": "hi"}]))
    assert response.status_code == 422


def test_put_rejects_an_id_that_is_not_a_uuid_with_422(client):
    response = client.put("/ai/conversations/not-a-uuid", json=_body())
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Secret scrub: a credential the assistant was handed never reaches disk
# ---------------------------------------------------------------------------


def test_a_posted_api_key_never_reaches_disk(client):
    messages = [
        {"role": "user", "content": "configure it"},
        {
            "role": "assistant",
            "content": "",
            "toolCalls": [
                {
                    "id": "tc1",
                    "name": "configure_plugin",
                    "args": {"plugin_id": "weather", "config": {"api_key": "sk-live-secret", "city": "NYC"}},
                    "phase": "ok",
                    "result": {"status": "ok", "result": {"headers": {"Authorization": "Bearer x"}, "token": "t"}},
                }
            ],
        },
    ]
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=messages))
    assert response.status_code == 201, response.text

    on_disk = _store_path().read_text()
    assert "sk-live-secret" not in on_disk
    assert "Bearer x" not in on_disk
    stored = json.loads(on_disk)["conversations"][0]["messages"][1]["toolCalls"][0]
    assert stored["args"]["config"] == {"api_key": "***", "city": "NYC"}
    assert stored["result"]["result"] == {"headers": "***", "token": "***"}
    # The response is the scrubbed record too, so a re-PUT of what the
    # client read back cannot smuggle the value in.
    assert response.json()["messages"][1]["toolCalls"][0]["args"]["config"]["api_key"] == "***"


def test_an_already_masked_secret_stays_masked(client):
    messages = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "", "toolCalls": [{"id": "t", "name": "n", "args": {"password": "***"}}]},
    ]
    response = client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=messages))
    assert response.json()["messages"][1]["toolCalls"][0]["args"]["password"] == "***"


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------


def test_list_is_newest_first_and_carries_summaries_not_transcripts(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=_transcript("First chat")))
    client.put(f"/ai/conversations/{CONV_B}", json=_body(messages=_transcript("Second chat")))
    # Touch A again so it becomes the most recently updated.
    client.put(
        f"/ai/conversations/{CONV_A}",
        json=_body(messages=[*_transcript("First chat"), {"role": "user", "content": "more"}]),
    )

    body = client.get("/ai/conversations").json()
    assert body["total"] == 2
    assert [c["id"] for c in body["conversations"]] == [CONV_A, CONV_B]
    first = body["conversations"][0]
    assert first["title"] == "First chat"
    assert first["message_count"] == 3
    assert first["provider_id"] == "p1"
    assert first["model"] == "test-model"
    assert "messages" not in first


def test_list_filters_by_title_substring_case_insensitively(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body(messages=_transcript("Weather for the commute")))
    client.put(f"/ai/conversations/{CONV_B}", json=_body(messages=_transcript("Stock ticker")))
    body = client.get("/ai/conversations", params={"q": "WEATHER"}).json()
    assert [c["id"] for c in body["conversations"]] == [CONV_A]
    assert body["total"] == 1


def test_get_returns_the_full_transcript(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    body = client.get(f"/ai/conversations/{CONV_A}").json()
    assert body["messages"] == _transcript()


def test_get_missing_is_404(client):
    response = client.get(f"/ai/conversations/{MISSING}")
    assert response.status_code == 404
    assert response.json() == {"detail": f"Conversation not found: {MISSING}"}


# ---------------------------------------------------------------------------
# Rename / delete / clear / export
# ---------------------------------------------------------------------------


def test_patch_renames(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    response = client.patch(f"/ai/conversations/{CONV_A}", json={"title": "  Renamed  "})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Renamed"
    assert client.get(f"/ai/conversations/{CONV_A}").json()["title"] == "Renamed"


def test_patch_rejects_a_blank_title_with_422(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    assert client.patch(f"/ai/conversations/{CONV_A}", json={"title": "   "}).status_code == 422


def test_patch_missing_is_404(client):
    assert client.patch(f"/ai/conversations/{MISSING}", json={"title": "x"}).status_code == 404


def test_delete_removes_one_and_answers_its_id(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    client.put(f"/ai/conversations/{CONV_B}", json=_body())
    response = client.delete(f"/ai/conversations/{CONV_A}")
    assert response.status_code == 200
    assert response.json() == {"id": CONV_A}
    assert client.get(f"/ai/conversations/{CONV_A}").status_code == 404
    assert client.get(f"/ai/conversations/{CONV_B}").status_code == 200


def test_delete_missing_is_404(client):
    assert client.delete(f"/ai/conversations/{MISSING}").status_code == 404


def test_clear_all_removes_everything_and_counts(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    client.put(f"/ai/conversations/{CONV_B}", json=_body())
    response = client.delete("/ai/conversations")
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
    assert client.get("/ai/conversations").json() == {"conversations": [], "total": 0}
    assert json.loads(_store_path().read_text())["conversations"] == []


def test_clear_all_on_an_empty_store_is_a_zero_count_success(client):
    assert client.delete("/ai/conversations").json() == {"deleted": 0}


def test_export_downloads_the_conversation_as_a_json_attachment(client):
    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    response = client.get(f"/ai/conversations/{CONV_A}/export")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == f'attachment; filename="fiestabot-conversation-{CONV_A}.json"'
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == client.get(f"/ai/conversations/{CONV_A}").json()


def test_export_missing_is_404(client):
    assert client.get(f"/ai/conversations/{MISSING}/export").status_code == 404


# ---------------------------------------------------------------------------
# The cap
# ---------------------------------------------------------------------------


def test_the_201st_conversation_evicts_the_least_recently_updated(client):
    from src.ai.conversations.storage import MAX_CONVERSATIONS

    assert MAX_CONVERSATIONS == 200
    ids = [f"{i:08x}-0000-4000-8000-000000000000" for i in range(MAX_CONVERSATIONS)]
    for cid in ids:
        assert client.put(f"/ai/conversations/{cid}", json=_body()).status_code == 201
    # ids[1] was updated least recently once ids[0] is touched again.
    client.put(f"/ai/conversations/{ids[0]}", json=_body())

    assert client.put(f"/ai/conversations/{CONV_A}", json=_body()).status_code == 201

    listing = client.get("/ai/conversations").json()
    assert listing["total"] == MAX_CONVERSATIONS
    listed = {c["id"] for c in listing["conversations"]}
    assert CONV_A in listed
    assert ids[0] in listed
    assert ids[1] not in listed


def test_updating_an_existing_conversation_at_the_cap_evicts_nothing(client):
    from src.ai.conversations.storage import MAX_CONVERSATIONS

    ids = [f"{i:08x}-0000-4000-8000-000000000000" for i in range(MAX_CONVERSATIONS)]
    for cid in ids:
        client.put(f"/ai/conversations/{cid}", json=_body())
    client.put(f"/ai/conversations/{ids[5]}", json=_body())
    assert client.get("/ai/conversations").json()["total"] == MAX_CONVERSATIONS


# ---------------------------------------------------------------------------
# Persistence: what one process wrote, the next one reads
# ---------------------------------------------------------------------------


def test_a_conversation_survives_a_fresh_service(client):
    from src.ai.conversations.service import ConversationService

    client.put(f"/ai/conversations/{CONV_A}", json=_body())
    fresh = ConversationService()
    stored = fresh.get(CONV_A)
    assert stored is not None
    assert stored.title == "Build a weather page"
    assert [m.role for m in stored.messages] == ["user", "assistant"]
    on_disk = json.loads(_store_path().read_text())
    assert on_disk["schema_version"] == 1

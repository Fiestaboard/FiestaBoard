"""Per-install identifier files (Plex client identifier, OpenAI agent host id).

They are read on hot paths (``GET /oauth/connections`` builds the ChatGPT
target), so a lost first-use race, a file left empty by a crash, or an
unwritable data dir must never raise.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.ai import sign_in
from src.oauth import plex

LOADERS = [
    pytest.param(plex.load_client_identifier, ".oauth_client_identifier", id="plex"),
    pytest.param(sign_in.load_agent_host_id, ".oauth_agent_host_id", id="agent_host"),
]


@pytest.mark.parametrize(("load", "name"), LOADERS)
def test_an_empty_file_is_regenerated_and_kept(tmp_path, load, name):
    (tmp_path / name).write_text("")
    first = load(tmp_path)
    assert first
    assert load(tmp_path) == first
    assert (tmp_path / name).read_text().strip() == first


@pytest.mark.parametrize(("load", "name"), LOADERS)
def test_losing_the_first_use_race_returns_the_winners_id(tmp_path, monkeypatch, load, name):
    (tmp_path / name).write_text("test-winner-id")
    # The loser saw no file yet; another request created it in between.
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert load(tmp_path) == "test-winner-id"


@pytest.mark.parametrize(("load", "name"), LOADERS)
def test_an_unwritable_data_dir_gives_a_stable_id_without_raising(tmp_path, monkeypatch, load, name):
    real_open = os.open

    def refuse(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:
            raise PermissionError(13, "read-only file system", path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse)
    first = load(tmp_path)
    assert first
    assert load(tmp_path) == first
    assert not (tmp_path / name).exists()

"""``GET /logs`` must cost O(offset + limit), not O(bytes on disk).

Two halves, and the order matters.

**The goldens** (``TestReadContract``) are value-level pins on
:func:`src.log_store._read_logs_from_files` written against the *unmodified*
tree: ordering, dedupe, filter semantics, offsets past the end, blank and
unparseable lines. They are the zero-regression evidence — every one of them
passed before ``_read_logs_from_files`` was rewritten and passes after.

**The bound** (``TestReadIsBounded``) is the reproduction. The old reader
globbed ``app.log`` plus five 5 MB backups, ``readlines()``-ed each in full,
``json.loads``-ed every line into one list *plus* a ``seen`` set holding a
``(timestamp, message)`` tuple for the entire corpus, and only then sliced
``[offset:offset + limit]``. Returning 100 rows out of a full 33.5 MB log set
(177,720 entries) peaked at 191.6 MB — enough to OOM-kill a Pi 3B+, whose
1 GB is shared with the GPU. Against the smaller corpus these tests build,
the pre-fix numbers were::

    entries parsed        30000  (bound: 2000)
    files opened              6  (bound: 1)
    tracemalloc peak     23.5 MB (bound: 4 MB)

Counts, not wall-clock: they transfer off this machine.

Deliberate contract changes, each pinned below by a test that names it:

1. ``total`` is a **lower bound** once the scan stops early — the reader can
   no longer know the size of a corpus it deliberately did not read. It stays
   exact whenever the scan reaches the end (every filtered read that matches
   less than a page, and every small corpus). ``has_more`` is exact in all
   cases and remains the authoritative "is there another page" signal.
2. The ``seen`` set is bounded to a sliding window instead of the corpus.
   Duplicates only ever arise between the 500-entry in-memory ring and the
   newest lines of ``app.log`` — rotation writes each line to exactly one
   file — so a window covers every duplicate that can actually occur. Two
   entries sharing a ``(timestamp, message)`` from opposite ends of a 33 MB
   corpus are now both returned; that pairing needs identical timestamps
   hours apart.
3. A line that is not valid UTF-8 now skips that line. It used to raise out
   of ``readlines()`` and silently discard the whole file. Reverse-reading
   cannot un-yield the newer entries it already produced, so per-line is the
   only available granularity — and it is the better one.
"""

from __future__ import annotations

import json
import tracemalloc
from unittest.mock import patch

import pytest

from src import log_store


def _entry(ts: str, level: str = "INFO", logger: str = "src.main", message: str = "m") -> dict:
    return {"timestamp": ts, "level": level, "logger": logger, "message": message}


def _write(path, entries) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    """Point the reader at a scratch log dir with an empty in-memory ring."""
    directory = tmp_path / "logs"
    directory.mkdir()
    monkeypatch.setattr(log_store, "LOG_DIR", directory)
    with log_store._log_lock:
        saved = list(log_store._log_buffer)
        log_store._log_buffer.clear()
    yield directory
    with log_store._log_lock:
        log_store._log_buffer.clear()
        log_store._log_buffer.extend(saved)


class TestReadContract:
    """Value-level goldens. All of these passed before the rewrite."""

    def test_returns_entries_newest_first_within_a_file(self, log_dir):
        _write(log_dir / "app.log", [_entry("t1"), _entry("t2"), _entry("t3")])

        logs, total, has_more = log_store._read_logs_from_files(limit=10)

        assert [entry["timestamp"] for entry in logs] == ["t3", "t2", "t1"]
        assert (total, has_more) == (3, False)

    def test_reads_the_current_file_before_its_backups(self, log_dir):
        _write(log_dir / "app.log", [_entry("current")])
        _write(log_dir / "app.log.1", [_entry("backup1")])
        _write(log_dir / "app.log.2", [_entry("backup2")])

        logs, _, _ = log_store._read_logs_from_files(limit=10)

        assert [entry["timestamp"] for entry in logs] == ["current", "backup1", "backup2"]

    def test_reads_a_backup_index_even_when_an_earlier_one_is_missing(self, log_dir):
        """``app.log.3`` is still read with no ``app.log.1`` present."""
        _write(log_dir / "app.log", [_entry("current")])
        _write(log_dir / "app.log.3", [_entry("orphan")])

        logs, total, _ = log_store._read_logs_from_files(limit=10)

        assert [entry["timestamp"] for entry in logs] == ["current", "orphan"]
        assert total == 2

    def test_puts_the_in_memory_ring_ahead_of_every_file_entry(self, log_dir):
        _write(log_dir / "app.log", [_entry("file")])
        with log_store._log_lock:
            log_store._log_buffer.append(_entry("mem-old"))
            log_store._log_buffer.append(_entry("mem-new"))

        logs, total, _ = log_store._read_logs_from_files(limit=10)

        assert [entry["timestamp"] for entry in logs] == ["mem-new", "mem-old", "file"]
        assert total == 3

    def test_the_ring_copy_wins_when_a_timestamp_and_message_repeat(self, log_dir):
        """Dedupe key is ``(timestamp, message)``; the earlier one survives."""
        _write(log_dir / "app.log", [_entry("t1", level="ERROR", logger="from.file")])
        with log_store._log_lock:
            log_store._log_buffer.append(_entry("t1", level="INFO", logger="from.ring"))

        logs, total, _ = log_store._read_logs_from_files(limit=10)

        assert len(logs) == 1
        assert logs[0]["logger"] == "from.ring"
        assert total == 1

    def test_dedupe_runs_before_filtering_so_a_shadowed_entry_stays_hidden(self, log_dir):
        """The ring's DEBUG copy suppresses the file's ERROR copy entirely."""
        _write(log_dir / "app.log", [_entry("t1", level="ERROR")])
        with log_store._log_lock:
            log_store._log_buffer.append(_entry("t1", level="DEBUG"))

        logs, total, has_more = log_store._read_logs_from_files(limit=10, level="ERROR")

        assert (logs, total, has_more) == ([], 0, False)

    def test_skips_blank_and_unparseable_lines(self, log_dir):
        with open(log_dir / "app.log", "w", encoding="utf-8") as f:
            f.write(json.dumps(_entry("t1")) + "\n")
            f.write("\n")
            f.write("   \n")
            f.write("not json at all\n")
            f.write('{"truncated": \n')
            f.write(json.dumps(_entry("t2")) + "\n")

        logs, total, _ = log_store._read_logs_from_files(limit=10)

        assert [entry["timestamp"] for entry in logs] == ["t2", "t1"]
        assert total == 2

    def test_tolerates_a_final_line_with_no_trailing_newline(self, log_dir):
        with open(log_dir / "app.log", "w", encoding="utf-8") as f:
            f.write(json.dumps(_entry("t1")) + "\n")
            f.write(json.dumps(_entry("t2")))

        logs, total, _ = log_store._read_logs_from_files(limit=10)

        assert [entry["timestamp"] for entry in logs] == ["t2", "t1"]
        assert total == 2

    def test_missing_log_directory_reads_as_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(log_store, "LOG_DIR", tmp_path / "nope")
        with log_store._log_lock:
            log_store._log_buffer.clear()

        assert log_store._read_logs_from_files(limit=10) == ([], 0, False)

    def test_level_filter_is_case_insensitive_and_exact(self, log_dir):
        _write(log_dir / "app.log", [_entry("t1", level="INFO"), _entry("t2", level="ERROR")])

        logs, total, has_more = log_store._read_logs_from_files(limit=10, level="error")

        assert [entry["timestamp"] for entry in logs] == ["t2"]
        assert (total, has_more) == (1, False)

    def test_search_matches_message_or_logger_case_insensitively(self, log_dir):
        _write(
            log_dir / "app.log",
            [
                _entry("t1", message="Board REFUSED the key"),
                _entry("t2", logger="src.utils.WEATHER", message="ok"),
                _entry("t3", message="unrelated"),
            ],
        )

        by_message, _, _ = log_store._read_logs_from_files(limit=10, search="refused")
        by_logger, _, _ = log_store._read_logs_from_files(limit=10, search="weather")

        assert [entry["timestamp"] for entry in by_message] == ["t1"]
        assert [entry["timestamp"] for entry in by_logger] == ["t2"]

    def test_search_and_level_compose(self, log_dir):
        _write(
            log_dir / "app.log",
            [
                _entry("t1", level="ERROR", message="board refused"),
                _entry("t2", level="INFO", message="board refused"),
                _entry("t3", level="ERROR", message="all good"),
            ],
        )

        logs, total, _ = log_store._read_logs_from_files(limit=10, level="ERROR", search="refused")

        assert [entry["timestamp"] for entry in logs] == ["t1"]
        assert total == 1

    def test_paginates_with_offset_and_reports_has_more(self, log_dir):
        _write(log_dir / "app.log", [_entry(f"t{i}") for i in range(10)])

        page, _total, has_more = log_store._read_logs_from_files(limit=3, offset=3)

        assert [entry["timestamp"] for entry in page] == ["t6", "t5", "t4"]
        assert has_more is True

    def test_the_final_page_reports_no_more(self, log_dir):
        _write(log_dir / "app.log", [_entry(f"t{i}") for i in range(10)])

        page, total, has_more = log_store._read_logs_from_files(limit=4, offset=6)

        assert [entry["timestamp"] for entry in page] == ["t3", "t2", "t1", "t0"]
        assert (total, has_more) == (10, False)

    def test_an_offset_past_the_end_is_an_empty_page_with_the_true_total(self, log_dir):
        _write(log_dir / "app.log", [_entry(f"t{i}") for i in range(5)])

        page, total, has_more = log_store._read_logs_from_files(limit=10, offset=500)

        assert (page, total, has_more) == ([], 5, False)

    def test_entries_are_returned_verbatim(self, log_dir):
        """No reshaping: whatever the JSON line held is what comes back."""
        weird = {"timestamp": "t1", "message": "m", "extra": {"nested": [1, 2]}}
        _write(log_dir / "app.log", [weird])

        logs, _, _ = log_store._read_logs_from_files(limit=10)

        assert logs == [weird]


class _CountingJson:
    """A ``json`` stand-in that counts ``loads`` calls."""

    def __init__(self, real):
        self._real = real
        self.loads_calls = 0

    def loads(self, *args, **kwargs):
        self.loads_calls += 1
        return self._real.loads(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


CORPUS_FILES = 6
ENTRIES_PER_FILE = 5000
TOTAL_ENTRIES = CORPUS_FILES * ENTRIES_PER_FILE


@pytest.fixture
def big_corpus(log_dir):
    """Six rotated files of realistic JSON log lines, newest in ``app.log``."""
    levels = ("DEBUG", "INFO", "WARNING", "ERROR")
    for file_index in range(CORPUS_FILES):
        name = "app.log" if file_index == 0 else f"app.log.{file_index}"
        # file 0 is newest, so its sequence numbers are the highest.
        base = (CORPUS_FILES - 1 - file_index) * ENTRIES_PER_FILE
        with open(log_dir / name, "w", encoding="utf-8") as f:
            for i in range(ENTRIES_PER_FILE):
                seq = base + i
                f.write(
                    json.dumps(
                        {
                            "timestamp": f"2026-09-06T00:00:{seq:06d}Z",
                            "level": levels[seq % len(levels)],
                            "logger": "src.displays.service",
                            "message": f"rendered page {seq} in {seq % 97} ms and sent it to the board",
                        }
                    )
                    + "\n"
                )
    return log_dir


class TestReadIsBounded:
    """The reproduction: cost must track the page, not the corpus."""

    def test_a_hundred_row_page_does_not_parse_the_whole_corpus(self, big_corpus, monkeypatch):
        counter = _CountingJson(json)
        monkeypatch.setattr(log_store, "json", counter)

        logs, _, has_more = log_store._read_logs_from_files(limit=100, offset=0)

        assert len(logs) == 100
        assert has_more is True
        # Old reader: 30000. A page of 100 needs 101 entries plus slack for
        # blank lines and read-ahead within one chunk.
        assert counter.loads_calls < 2000, f"parsed {counter.loads_calls} entries for a 100-row page"

    def test_a_hundred_row_page_does_not_open_every_backup(self, big_corpus):
        opened = []
        real_open = open

        def tracking_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        import builtins

        builtins.open = tracking_open
        try:
            log_store._read_logs_from_files(limit=100, offset=0)
        finally:
            builtins.open = real_open

        # Old reader opened all six. The newest alone covers a 100-row page.
        assert len(opened) == 1, opened
        assert opened[0].endswith("app.log")

    def test_a_hundred_row_page_stays_under_a_few_megabytes(self, big_corpus):
        tracemalloc.start()
        try:
            tracemalloc.reset_peak()
            logs, _, _ = log_store._read_logs_from_files(limit=100, offset=0)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert len(logs) == 100
        # Old reader peaked at 23.5 MB on this corpus (191.6 MB on a full
        # 33.5 MB one). 4 MB leaves room for one reverse-read chunk.
        assert peak < 4 * 1024 * 1024, f"peak {peak / 1024 / 1024:.1f} MB for a 100-row page"

    def test_a_deep_offset_still_only_reads_what_it_must(self, big_corpus, monkeypatch):
        counter = _CountingJson(json)
        monkeypatch.setattr(log_store, "json", counter)

        logs, _, has_more = log_store._read_logs_from_files(limit=50, offset=1000)

        assert len(logs) == 50
        assert has_more is True
        # offset + limit + 1 == 1051 entries are genuinely needed.
        assert counter.loads_calls < 3000, f"parsed {counter.loads_calls} entries for offset=1000"

    def test_a_filter_that_matches_nothing_still_reports_an_empty_page(self, big_corpus):
        """Correctness is not traded away: an exhaustive scan still happens
        when the filter forces one, and it still returns the true total."""
        logs, total, has_more = log_store._read_logs_from_files(limit=100, search="no such text anywhere")

        assert (logs, total, has_more) == ([], 0, False)

    def test_a_filter_that_matches_a_quarter_of_the_corpus_paginates_correctly(self, big_corpus):
        logs, _, has_more = log_store._read_logs_from_files(limit=10, level="ERROR")

        assert len(logs) == 10
        assert has_more is True
        assert {entry["level"] for entry in logs} == {"ERROR"}
        # Newest ERROR first, descending.
        seqs = [int(entry["timestamp"][-7:-1]) for entry in logs]
        assert seqs == sorted(seqs, reverse=True)


class TestTotalIsALowerBoundOnceTheScanStopsEarly:
    """Deliberate change #1, pinned so it cannot drift back silently."""

    def test_total_is_exact_when_the_scan_reaches_the_end(self, log_dir):
        _write(log_dir / "app.log", [_entry(f"t{i}") for i in range(40)])

        _, total, has_more = log_store._read_logs_from_files(limit=100)

        assert (total, has_more) == (40, False)

    def test_total_is_a_lower_bound_when_the_page_is_full(self, big_corpus):
        logs, total, has_more = log_store._read_logs_from_files(limit=100, offset=0)

        assert len(logs) == 100
        assert has_more is True
        # Not TOTAL_ENTRIES: the reader stopped one entry past the page.
        assert total == 101
        assert total < TOTAL_ENTRIES


class TestTheHandlerDoesNotStallTheEventLoop:
    """``GET /logs`` was a synchronous file read inside an ``async def``.

    1.53 s of blocking on a laptop; roughly 20 s of a wedged event loop at Pi
    speeds, during which nothing else — no schedule tick, no board send, no
    other request — makes progress. The read now goes to a worker thread.
    """

    def test_the_reader_runs_off_the_main_thread(self):
        import asyncio
        import threading

        from src.debug import routes

        threads: list[str] = []

        def spy(**kwargs):
            threads.append(threading.current_thread().name)
            return ([], 0, False)

        with patch("src.log_store._read_logs_from_files", side_effect=spy):
            response = asyncio.run(routes.get_logs(limit=10, offset=0, level=None, search=None))

        assert response.total == 0
        assert threads, "the handler never called the reader"
        assert threads[0] != threading.main_thread().name, "the reader ran on the event loop thread"

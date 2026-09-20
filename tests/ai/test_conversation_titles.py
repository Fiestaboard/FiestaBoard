"""How a saved conversation names itself (#2024).

A title is a thing the user scans in a list of twenty, so it is a phrase,
not the first 80 characters of a paragraph with the opening quote still
attached (which is what History showed before this).
"""

from src.ai.conversations.models import (
    TITLE_DERIVED_MAX_LENGTH,
    ConversationMessage,
    derive_title,
)


def _user(content: str) -> list[ConversationMessage]:
    return [ConversationMessage(role="user", content=content)]


def test_a_short_request_is_the_title_as_typed():
    assert derive_title(_user("Build a weather page")) == "Build a weather page"


def test_the_title_stops_at_the_first_sentence():
    messages = _user("Make a stocks page. Put AAPL and NVDA on it, and refresh every minute.")
    assert derive_title(messages) == "Make a stocks page"


def test_the_title_stops_at_a_clause_boundary():
    messages = _user('Set up a daily schedule for my board: show "Weekend Good Morning" from 7:00 to 9:00')
    assert derive_title(messages) == "Set up a daily schedule for my board"


def test_a_time_is_not_mistaken_for_a_clause_boundary():
    assert derive_title(_user("Show the 7:00 page")) == "Show the 7:00 page"


def test_surrounding_quotes_are_stripped():
    assert derive_title(_user('"Make it green"')) == "Make it green"


def test_trailing_punctuation_is_dropped():
    assert derive_title(_user("Can you delete the Goodnight entry?")) == "Can you delete the Goodnight entry"


def test_a_long_request_is_cut_at_a_word_boundary_with_an_ellipsis():
    messages = _user(
        "Please build me a page that shows the weather and the transit times and the stock prices together"
    )
    title = derive_title(messages)
    assert len(title) <= TITLE_DERIVED_MAX_LENGTH
    assert title.endswith("…")
    assert not title.rstrip("…").endswith(" ")
    # Cut between words, never through one.
    assert title == "Please build me a page that shows the weather…"


def test_a_single_very_long_word_is_still_cut_to_the_limit():
    title = derive_title(_user("x" * 200))
    assert len(title) <= TITLE_DERIVED_MAX_LENGTH
    assert title.endswith("…")


def test_only_the_first_line_is_considered():
    assert derive_title(_user("Fix the board\nIt shows yesterday's date")) == "Fix the board"


def test_an_assistant_first_transcript_still_finds_the_user_line():
    messages = [
        ConversationMessage(role="assistant", content="Hello!"),
        ConversationMessage(role="user", content="Make a clock page"),
    ]
    assert derive_title(messages) == "Make a clock page"


def test_a_transcript_with_nothing_from_the_user_is_untitled():
    assert derive_title([ConversationMessage(role="assistant", content="Hello!")]) == "Untitled chat"


def test_a_masked_secret_still_reads_as_a_title():
    # The scrub runs before this; the title must not re-break on "***".
    assert derive_title(_user("use *** for the weather plugin")) == "use *** for the weather plugin"

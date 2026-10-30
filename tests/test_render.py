from video2notes.onscreen import OnScreenLine
from video2notes.render import render_note, spoken_paragraphs, timestamp
from video2notes.transcript import Segment

URL = "https://www.youtube.com/watch?v=abc123"


def test_timestamp_formats():
    assert timestamp(0) == "00:00"
    assert timestamp(75.9) == "01:15"
    assert timestamp(3725) == "1:02:05"


def test_spoken_paragraphs_split_about_every_30_seconds():
    segments = [Segment(0, "a"), Segment(10, "b"), Segment(31, "c"), Segment(45, "d"), Segment(62, "e")]

    assert spoken_paragraphs(segments) == [(0, "a b"), (31, "c d"), (62, "e")]


def test_note_has_title_source_and_both_sections_in_order():
    note = render_note(
        "Demo video",
        URL,
        [Segment(0, "Welcome."), Segment(5, "Let's start.")],
        [OnScreenLine(1.0, "Step 1"), OnScreenLine(1.0, "pip install x"), OnScreenLine(12.0, "Step 2")],
    )

    assert note.startswith("# Demo video\n")
    assert f"Source: <{URL}>" in note
    assert note.index("## Spoken") < note.index("---") < note.index("## On screen")
    assert "**[00:00]** Welcome. Let's start." in note
    assert "- **[00:01]** Step 1 · pip install x" in note
    assert "- **[00:12]** Step 2" in note
    assert [line for line in note.splitlines() if line.startswith("## ")] == ["## Spoken", "## On screen"]


def test_empty_and_skipped_tracks_say_so():
    empty = render_note("T", URL, [], [])
    skipped = render_note("T", URL, [Segment(0, "hi")], None)

    assert "No transcript was returned" in empty
    assert "No on-screen text was found" in empty
    assert "Skipped" in skipped

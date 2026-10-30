"""Render one markdown note with the spoken track and the on-screen track kept apart."""

from __future__ import annotations

from itertools import groupby
from typing import Sequence

from video2notes.onscreen import OnScreenLine
from video2notes.transcript import Segment

PARAGRAPH_SECONDS = 30.0


def timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def spoken_paragraphs(segments: Sequence[Segment], span: float = PARAGRAPH_SECONDS) -> list[tuple[float, str]]:
    """Join transcript segments into paragraphs of about ``span`` seconds each."""
    paragraphs: list[tuple[float, str]] = []
    start: float | None = None
    words: list[str] = []
    for segment in segments:
        if start is None:
            start = segment.start
        elif segment.start - start >= span:
            paragraphs.append((start, " ".join(words)))
            start, words = segment.start, []
        words.append(segment.text)
    if start is not None and words:
        paragraphs.append((start, " ".join(words)))
    return paragraphs


def render_note(
    title: str,
    url: str,
    segments: Sequence[Segment],
    onscreen: Sequence[OnScreenLine] | None,
) -> str:
    """Build the note. Pass ``onscreen=None`` when the on-screen track was skipped."""
    out = [f"# {title}", "", f"Source: <{url}>", ""]

    out += ["## Spoken", "", "_What is said, from the video's transcript._", ""]
    paragraphs = spoken_paragraphs(segments)
    if paragraphs:
        for start, text in paragraphs:
            out += [f"**[{timestamp(start)}]** {text}", ""]
    else:
        out += ["_No transcript was returned for this video._", ""]

    out += ["---", ""]

    out += ["## On screen", "", "_Text that appears in the frames, read with OCR. Expect some misreads._", ""]
    if onscreen is None:
        out += ["_Skipped (run without `--no-onscreen` to include it)._", ""]
    elif not onscreen:
        out += ["_No on-screen text was found._", ""]
    else:
        for start, group in groupby(onscreen, key=lambda line: line.start):
            out.append(f"- **[{timestamp(start)}]** " + " · ".join(line.text for line in group))
        out.append("")

    return "\n".join(out).rstrip() + "\n"

"""Read the text that appears on screen in a video.

1. Download the video with yt-dlp (public videos only, no logins or cookies).
2. Pull keyframes with ffmpeg: every scene change (``select='gt(scene,0.3)'``),
   plus at least one frame every 2 seconds so slow fades and static slides are not missed.
3. OCR each frame with tesseract, keeping only lines it reads with confidence.
4. Drop junk and near-duplicate lines, so a caption that stays up for ten seconds
   appears once, at the moment it first showed up.
"""

from __future__ import annotations

import difflib
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

SCENE_THRESHOLD = 0.3
FLOOR_SECONDS = 2.0
SIMILARITY_THRESHOLD = 0.85
MIN_CONFIDENCE = 75.0
MAX_HEIGHT = 720

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


class OnScreenError(RuntimeError):
    """On-screen text could not be extracted."""


@dataclass(frozen=True)
class Frame:
    start: float
    path: Path


@dataclass(frozen=True)
class OnScreenLine:
    """A line of on-screen text and the time (in seconds) it first appeared."""

    start: float
    text: str


@dataclass(frozen=True)
class Download:
    path: Path
    title: str


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)


def require_tools(names: Sequence[str] = ("ffmpeg", "tesseract")) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise OnScreenError(
            "Missing required program(s): " + ", ".join(missing) + ". "
            "Install them first (macOS: `brew install ffmpeg tesseract`)."
        )


def download_video(url: str, workdir: Path) -> Download:
    """Download a public video into ``workdir`` and return its path and title."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    options = {
        # Video only, small enough for fast OCR. Audio is not needed for this track.
        "format": f"bv*[height<={MAX_HEIGHT}]/b[height<={MAX_HEIGHT}]/bv*/b",
        "outtmpl": str(workdir / "video.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise OnScreenError(f"Could not download the video: {exc}") from exc

    downloads = info.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else Path(ydl.prepare_filename(info))
    if not path.exists():
        raise OnScreenError("The video download did not produce a file.")
    return Download(path=path, title=info.get("title") or url)


def video_title(url: str) -> str:
    """Look up a video's title without downloading it. Falls back to the URL."""
    from yt_dlp import YoutubeDL

    try:
        with YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:  # a title is nice to have; never fail the run over it
        return url
    return (info or {}).get("title") or url


def keyframe_filter(scene_threshold: float = SCENE_THRESHOLD, floor_seconds: float = FLOOR_SECONDS) -> str:
    """ffmpeg filter: keep the first frame, every scene change, and one frame per ``floor_seconds``."""
    select = (
        f"gt(scene,{scene_threshold})"
        f"+isnan(prev_selected_t)"
        f"+gte(t-prev_selected_t,{floor_seconds})"
    )
    return f"select='{select}',showinfo"


_PTS_TIME = re.compile(r"pts_time:\s*([0-9]+(?:\.[0-9]+)?)")


def parse_showinfo(stderr: str) -> list[float]:
    """Read frame timestamps (seconds) from ffmpeg's showinfo log, in output order."""
    return [float(m.group(1)) for line in stderr.splitlines() if "Parsed_showinfo" in line
            for m in [_PTS_TIME.search(line)] if m]


def extract_keyframes(
    video: Path,
    outdir: Path,
    *,
    scene_threshold: float = SCENE_THRESHOLD,
    floor_seconds: float = FLOOR_SECONDS,
    run: Runner = _run,
) -> list[Frame]:
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", str(video),
        "-vf", keyframe_filter(scene_threshold, floor_seconds),
        "-fps_mode", "vfr",
        str(outdir / "frame_%05d.png"),
    ]
    proc = run(cmd)
    if proc.returncode != 0:
        raise OnScreenError(f"ffmpeg failed: {proc.stderr.strip()[-500:]}")

    times = parse_showinfo(proc.stderr)
    files = sorted(outdir.glob("frame_*.png"))
    # showinfo logs once per frame written, so the two lists line up one to one.
    return [Frame(start=t, path=p) for t, p in zip(times, files)]


def parse_tsv(tsv: str, min_confidence: float = MIN_CONFIDENCE) -> list[str]:
    """Rebuild text lines from tesseract's TSV output, keeping confident lines only.

    Each TSV row is one word with a 0-100 confidence score. Words are grouped back into
    lines, and a line is kept when its average confidence reaches ``min_confidence``.
    Low-confidence lines are almost always texture, icons or motion blur read as letters.
    """
    lines: dict[tuple[str, str, str, str], list[tuple[str, float]]] = {}
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":  # level 5 = a word
            continue
        word = cols[11].strip()
        if not word:
            continue
        try:
            confidence = float(cols[10])
        except ValueError:
            continue
        lines.setdefault((cols[1], cols[2], cols[3], cols[4]), []).append((word, confidence))

    kept = []
    for words in lines.values():
        if sum(conf for _, conf in words) / len(words) >= min_confidence:
            kept.append(" ".join(word for word, _ in words))
    return kept


def ocr_frame(path: Path, *, run: Runner = _run, min_confidence: float = MIN_CONFIDENCE) -> list[str]:
    proc = run(["tesseract", str(path), "stdout", "--psm", "3", "tsv"])
    return parse_tsv(proc.stdout, min_confidence) if proc.returncode == 0 else []


def clean_line(raw: str) -> str | None:
    """Return a tidy line, or None when the OCR output is noise."""
    line = " ".join(raw.split())
    if len(line) < 3:
        return None
    letters_digits = sum(ch.isalnum() for ch in line)
    if letters_digits / len(line.replace(" ", "")) < 0.6:
        return None
    if not re.search(r"[A-Za-z]{2,}", line):
        return None
    return line


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def dedupe(lines: Sequence[OnScreenLine], threshold: float = SIMILARITY_THRESHOLD) -> list[OnScreenLine]:
    """Keep the first sighting of each line; drop later lines that are near-identical."""
    kept: list[OnScreenLine] = []
    seen: list[str] = []
    for line in sorted(lines, key=lambda item: item.start):
        key = _normalise(line.text)
        if not key:
            continue
        duplicate = False
        for other in seen:
            # A partial read of a line we already have (cut off by a transition) adds nothing.
            if len(key) >= 8 and key in other:
                duplicate = True
                break
            matcher = difflib.SequenceMatcher(None, key, other)
            if matcher.real_quick_ratio() >= threshold and matcher.ratio() >= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(line)
            seen.append(key)
    return kept


def text_from_frames(frames: Sequence[Frame], *, run: Runner = _run) -> list[OnScreenLine]:
    lines = []
    for frame in frames:
        for raw in ocr_frame(frame.path, run=run):
            line = clean_line(raw)
            if line:
                lines.append(OnScreenLine(start=frame.start, text=line))
    return dedupe(lines)


def extract_onscreen_text(
    video: Path,
    workdir: Path,
    *,
    scene_threshold: float = SCENE_THRESHOLD,
    floor_seconds: float = FLOOR_SECONDS,
) -> list[OnScreenLine]:
    require_tools()
    frames = extract_keyframes(
        video, workdir / "frames", scene_threshold=scene_threshold, floor_seconds=floor_seconds
    )
    return text_from_frames(frames)

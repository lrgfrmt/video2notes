"""Command line entry point: ``video2notes <url> -o notes.md``."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from video2notes import __version__
from video2notes.onscreen import (
    FLOOR_SECONDS,
    SCENE_THRESHOLD,
    OnScreenError,
    download_video,
    extract_onscreen_text,
    video_title,
)
from video2notes.render import render_note
from video2notes.transcript import TranscriptError, fetch_transcript


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video2notes",
        description="Turn a public video into one markdown note: what is said, and what is shown on screen.",
    )
    parser.add_argument("url", help="URL of a public video (YouTube, TikTok, Instagram, X, ...)")
    parser.add_argument("-o", "--output", default="notes.md", help="where to write the note (default: notes.md)")
    parser.add_argument("--lang", help="preferred transcript language, as an ISO 639-1 code such as en")
    parser.add_argument(
        "--mode",
        choices=["auto", "native", "generate"],
        default="auto",
        help="native: existing captions only; generate: transcribe the audio; auto: captions first (default)",
    )
    parser.add_argument("--no-onscreen", action="store_true", help="skip the download and OCR step")
    parser.add_argument("--scene-threshold", type=float, default=SCENE_THRESHOLD,
                        help=f"ffmpeg scene-change threshold (default: {SCENE_THRESHOLD})")
    parser.add_argument("--floor-seconds", type=float, default=FLOOR_SECONDS,
                        help=f"take at least one frame this often, in seconds (default: {FLOOR_SECONDS})")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        print("Fetching transcript with Supadata...", file=sys.stderr)
        transcript = fetch_transcript(args.url, lang=args.lang, mode=args.mode)

        onscreen = None
        if args.no_onscreen:
            title = video_title(args.url)
        else:
            with tempfile.TemporaryDirectory(prefix="video2notes-") as tmp:
                workdir = Path(tmp)
                print("Downloading video for on-screen text...", file=sys.stderr)
                download = download_video(args.url, workdir)
                title = download.title
                print("Reading on-screen text (ffmpeg + tesseract)...", file=sys.stderr)
                onscreen = extract_onscreen_text(
                    download.path,
                    workdir,
                    scene_threshold=args.scene_threshold,
                    floor_seconds=args.floor_seconds,
                )
    except (TranscriptError, OnScreenError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    note = render_note(title, args.url, transcript.segments, onscreen)
    output = Path(args.output)
    output.write_text(note, encoding="utf-8")
    spoken = len(transcript.segments)
    shown = "skipped" if onscreen is None else len(onscreen)
    print(f"Wrote {output} ({spoken} transcript segments, {shown} on-screen lines).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

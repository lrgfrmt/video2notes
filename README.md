# video2notes

Turn a public video into one markdown note: what is **said**, and what is **shown on screen**.

<a href="https://supadata.ai/r/Z6NXWKCP" rel="sponsored" target="_blank"><img src="https://supadata.ai/badge/powered-by-supadata-light.svg" alt="Powered by Supadata" width="232" height="54" /></a>

## Why two tracks

Most "video to notes" tools only use the audio. That misses a lot. Tutorials show the command
instead of reading it out. Reels and Shorts put the key point in a caption and never say it.
Slides carry the numbers while the speaker talks around them.

video2notes keeps two tracks and puts both in the note:

- **Spoken**: the transcript, fetched with the official [Supadata](https://supadata.ai) Python SDK.
- **On screen**: text read from the video frames with ffmpeg and tesseract, with timestamps.

They stay in separate sections, so you can always tell what was said from what was shown.

## Install

You need Python 3.10 or newer, plus `ffmpeg` and `tesseract` on your `PATH`.

```bash
# macOS
brew install ffmpeg tesseract
# Debian / Ubuntu
sudo apt install ffmpeg tesseract-ocr
```

Then install video2notes:

```bash
git clone https://github.com/lrgfrmt/video2notes.git
cd video2notes
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

The transcript job-polling call (`transcript.get_job_status`) arrived in version 1.7.0 of the
Supadata SDK. Until 1.7.0 is on PyPI, `pyproject.toml` installs the SDK from its official GitHub
repository at a pinned commit.

## Quick start

```bash
export SUPADATA_API_KEY=your-key-here   # see .env.example
video2notes "https://www.youtube.com/watch?v=_20US068pzk" -o notes.md
```

Useful options:

| Option | What it does |
| --- | --- |
| `-o notes.md` | Where to write the note (default `notes.md`) |
| `--mode native` | Use existing captions only. `generate` transcribes the audio; `auto` (default) tries captions first |
| `--lang en` | Preferred transcript language |
| `--no-onscreen` | Transcript only: skip the download and OCR |
| `--scene-threshold 0.3` | How big a visual change counts as a new scene |
| `--floor-seconds 2` | Take at least one frame this often |

See [`examples/sample-output.md`](examples/sample-output.md) for a real note.

## How it works

1. **Transcript** (`video2notes/transcript.py`). One call to `supadata.transcript(url=..., mode=...)`.
   If the video has captions, Supadata returns the transcript straight away. If it has to
   generate one, it returns a job ID instead, and the tool polls
   `supadata.transcript.get_job_status(job_id)` every 2 seconds until the job completes or fails.
2. **On-screen text** (`video2notes/onscreen.py`). The video is downloaded with
   [yt-dlp](https://github.com/yt-dlp/yt-dlp) at up to 720p. ffmpeg keeps a frame at every scene
   change (`select='gt(scene,0.3)'`) and at least one frame every 2 seconds. tesseract reads each
   frame, and only lines it reads with confidence are kept. Repeats are dropped: a caption that
   stays up for ten seconds is listed once, at the moment it first appeared.
3. **Note** (`video2notes/render.py`). A title, the source link, then `## Spoken` in timestamped
   paragraphs of about 30 seconds, a divider, and `## On screen` as a timestamped list.

The API key is read from the `SUPADATA_API_KEY` environment variable only. It is never printed or
written to the note.

## Limits

- **Public videos only.** There is no support for logins, cookies, private or members-only videos,
  and there will not be.
- **OCR is not perfect.** Stylised fonts, motion blur and busy backgrounds cause misreads. The
  on-screen section says so.
- **Credits.** Each run makes one transcript request to Supadata, plus status checks if a job has
  to be generated. Credits per call are listed at <https://supadata.ai/pricing>. Use
  `--mode native` if you only want existing captions and never an AI-generated transcript.
- The download and OCR happen on your machine and use no Supadata credits.

## Get a Supadata API key

[Get a Supadata API key](https://supadata.ai/r/Z6NXWKCP) (referral link).

## Tutorial

A step-by-step walkthrough of how this was built: <https://www.lrgfrmt.com/lab/video-to-notes>

## License

[MIT](LICENSE)

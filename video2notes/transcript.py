"""Fetch a timestamped transcript with the official Supadata Python SDK.

Supadata answers a transcript request in one of two ways:

* straight away, with the transcript itself, or
* with a job ID, when the transcript has to be generated first. In that case we
  poll ``transcript.get_job_status(job_id)`` until the job completes or fails.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from supadata import Supadata, SupadataError

API_KEY_ENV = "SUPADATA_API_KEY"

POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 300.0


class TranscriptError(RuntimeError):
    """The transcript could not be fetched."""


@dataclass(frozen=True)
class Segment:
    """One piece of the transcript. ``start`` is in seconds from the start of the video."""

    start: float
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    segments: list[Segment]
    lang: str


def client_from_env() -> Supadata:
    """Build a client from the SUPADATA_API_KEY environment variable."""
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        raise TranscriptError(
            f"{API_KEY_ENV} is not set. Get a key from the Supadata dashboard and run "
            f"`export {API_KEY_ENV}=...` first."
        )
    return Supadata(api_key=api_key)


def fetch_transcript(
    url: str,
    client: Supadata | None = None,
    *,
    lang: str | None = None,
    mode: str = "auto",
    poll_interval: float = POLL_INTERVAL_SECONDS,
    timeout: float = POLL_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> TranscriptResult:
    """Return the transcript of ``url`` as timestamped segments.

    ``mode`` is passed to Supadata: ``native`` uses existing captions only,
    ``generate`` always transcribes the audio, and ``auto`` tries captions first.
    """
    client = client or client_from_env()
    try:
        result = client.transcript(url=url, lang=lang, text=False, mode=mode)
    except SupadataError as exc:
        raise TranscriptError(f"Supadata could not return a transcript: {exc}") from exc

    job_id = getattr(result, "job_id", None)
    if job_id:
        result = wait_for_job(
            client, job_id, poll_interval=poll_interval, timeout=timeout, sleep=sleep, clock=clock
        )

    return TranscriptResult(segments=to_segments(result.content), lang=result.lang or "")


def wait_for_job(
    client: Supadata,
    job_id: str,
    *,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    timeout: float = POLL_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Any:
    """Poll an asynchronous transcript job and return its transcript once completed."""
    deadline = clock() + timeout
    while True:
        try:
            job = client.transcript.get_job_status(job_id)
        except SupadataError as exc:
            raise TranscriptError(f"Could not check transcript job {job_id}: {exc}") from exc

        if job.status == "completed":
            if job.result is None:
                raise TranscriptError(f"Transcript job {job_id} completed without a transcript.")
            return job.result
        if job.status == "failed":
            raise TranscriptError(f"Transcript job {job_id} failed: {_describe_error(job.error)}")
        # Anything else ("queued", "active") means the job is still running.
        if clock() >= deadline:
            raise TranscriptError(
                f"Transcript job {job_id} was still '{job.status}' after {timeout:.0f} seconds."
            )
        sleep(poll_interval)


def to_segments(content: Any) -> list[Segment]:
    """Convert SDK transcript content (chunks with millisecond offsets, or plain text)."""
    if not content:
        return []
    if isinstance(content, str):
        return [Segment(start=0.0, text=content.strip())]
    segments = []
    for chunk in content:
        text = " ".join(str(chunk.text).split())
        if text:
            segments.append(Segment(start=chunk.offset / 1000.0, text=text))
    return segments


def _describe_error(error: Any) -> str:
    if not error:
        return "no reason given"
    if isinstance(error, dict):
        parts = [error.get("message"), error.get("details"), error.get("error")]
        return " | ".join(str(p) for p in parts if p) or "no reason given"
    return str(error)

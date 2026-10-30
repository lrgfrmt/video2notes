import pytest
from supadata import SupadataError
from supadata.types import BatchJob, Transcript, TranscriptJobResult

from video2notes import transcript as tr

URL = "https://www.youtube.com/watch?v=abc123"


class FakeTranscriptNamespace:
    """Stands in for ``client.transcript``: callable, with ``get_job_status``."""

    def __init__(self, first, statuses=()):
        self.first = first
        self.statuses = list(statuses)
        self.calls = []
        self.polled = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.first, Exception):
            raise self.first
        return self.first

    def get_job_status(self, job_id):
        self.polled.append(job_id)
        status = self.statuses.pop(0)
        if isinstance(status, Exception):
            raise status
        return status


class FakeClient:
    def __init__(self, first, statuses=()):
        self.transcript = FakeTranscriptNamespace(first, statuses)


def chunks(*items):
    return [{"text": text, "offset": offset, "duration": 1000, "lang": "en"} for offset, text in items]


def test_immediate_transcript_becomes_segments_in_seconds():
    client = FakeClient(Transcript(content=chunks((0, "Hello"), (2500, "  world  ")), lang="en"))

    result = tr.fetch_transcript(URL, client=client, mode="native")

    assert result.lang == "en"
    assert result.segments == [tr.Segment(0.0, "Hello"), tr.Segment(2.5, "world")]
    assert client.transcript.calls == [{"url": URL, "lang": None, "text": False, "mode": "native"}]
    assert client.transcript.polled == []


def test_job_is_polled_until_completed():
    done = Transcript(content=chunks((1000, "generated text")), lang="en")
    client = FakeClient(
        BatchJob(job_id="job-1"),
        statuses=[
            TranscriptJobResult(status="queued"),
            TranscriptJobResult(status="active"),
            TranscriptJobResult(status="completed", result=done),
        ],
    )
    sleeps = []

    result = tr.fetch_transcript(URL, client=client, sleep=sleeps.append, poll_interval=0.5)

    assert client.transcript.polled == ["job-1", "job-1", "job-1"]
    assert sleeps == [0.5, 0.5]
    assert result.segments == [tr.Segment(1.0, "generated text")]


def test_completed_job_result_dict_is_parsed_by_the_sdk():
    raw = {"content": chunks((0, "from dict")), "lang": "de"}
    client = FakeClient(BatchJob(job_id="job-2"), [TranscriptJobResult(status="completed", result=raw)])

    result = tr.fetch_transcript(URL, client=client, sleep=lambda _: None)

    assert result.lang == "de"
    assert result.segments == [tr.Segment(0.0, "from dict")]


def test_failed_job_raises_with_reason():
    client = FakeClient(
        BatchJob(job_id="job-3"),
        [TranscriptJobResult(status="failed", error={"error": "transcript-unavailable", "message": "No audio"})],
    )

    with pytest.raises(tr.TranscriptError, match="job-3 failed: No audio"):
        tr.fetch_transcript(URL, client=client, sleep=lambda _: None)


def test_job_that_never_finishes_times_out():
    client = FakeClient(BatchJob(job_id="job-4"), [TranscriptJobResult(status="active")] * 5)
    ticks = iter([0.0, 1.0, 2.0, 11.0])

    with pytest.raises(tr.TranscriptError, match="still 'active' after 10 seconds"):
        tr.fetch_transcript(URL, client=client, timeout=10, sleep=lambda _: None, clock=lambda: next(ticks))


def test_sdk_error_is_wrapped():
    error = SupadataError(error="not-found", message="Video not found", details="Check the URL")
    client = FakeClient(error)

    with pytest.raises(tr.TranscriptError, match="Video not found"):
        tr.fetch_transcript(URL, client=client)


def test_plain_text_content_becomes_one_segment():
    assert tr.to_segments("  just text ") == [tr.Segment(0.0, "just text")]
    assert tr.to_segments([]) == []
    assert tr.to_segments(None) == []


def test_missing_api_key_gives_a_clear_message(monkeypatch):
    monkeypatch.delenv(tr.API_KEY_ENV, raising=False)

    with pytest.raises(tr.TranscriptError, match="SUPADATA_API_KEY is not set"):
        tr.client_from_env()


def test_api_key_is_read_from_the_environment_and_never_echoed(monkeypatch, capsys):
    monkeypatch.setenv(tr.API_KEY_ENV, "test-key-not-real")

    client = tr.client_from_env()

    assert client.session.headers["x-api-key"] == "test-key-not-real"
    captured = capsys.readouterr()
    assert "test-key-not-real" not in captured.out + captured.err

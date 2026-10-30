from pathlib import Path

from video2notes import cli
from video2notes.onscreen import Download, OnScreenLine
from video2notes.transcript import Segment, TranscriptError, TranscriptResult

URL = "https://www.youtube.com/watch?v=abc123"


def test_cli_writes_a_note_with_both_tracks(tmp_path, monkeypatch):
    seen = {}

    def fake_fetch(url, lang=None, mode="auto"):
        seen["fetch"] = (url, lang, mode)
        return TranscriptResult(segments=[Segment(0, "Hello from the audio.")], lang="en")

    def fake_download(url, workdir):
        video = Path(workdir) / "video.mp4"
        video.write_bytes(b"")
        return Download(path=video, title="Sample title")

    def fake_onscreen(video, workdir, scene_threshold, floor_seconds):
        seen["onscreen"] = (scene_threshold, floor_seconds)
        return [OnScreenLine(3.0, "Text only on screen")]

    monkeypatch.setattr(cli, "fetch_transcript", fake_fetch)
    monkeypatch.setattr(cli, "download_video", fake_download)
    monkeypatch.setattr(cli, "extract_onscreen_text", fake_onscreen)
    out = tmp_path / "notes.md"

    code = cli.main([URL, "-o", str(out), "--mode", "native", "--lang", "en"])

    assert code == 0
    note = out.read_text(encoding="utf-8")
    assert note.startswith("# Sample title")
    assert "Hello from the audio." in note
    assert "- **[00:03]** Text only on screen" in note
    assert seen == {"fetch": (URL, "en", "native"), "onscreen": (0.3, 2.0)}


def test_cli_no_onscreen_skips_the_download(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "fetch_transcript", lambda url, lang=None, mode="auto": TranscriptResult([], ""))
    monkeypatch.setattr(cli, "video_title", lambda url: "Looked-up title")
    monkeypatch.setattr(cli, "download_video", lambda *a: (_ for _ in ()).throw(AssertionError("no download")))
    out = tmp_path / "n.md"

    assert cli.main([URL, "-o", str(out), "--no-onscreen"]) == 0
    assert "Skipped" in out.read_text(encoding="utf-8")


def test_cli_reports_errors_and_exits_non_zero(tmp_path, monkeypatch, capsys):
    def failing(url, lang=None, mode="auto"):
        raise TranscriptError("SUPADATA_API_KEY is not set.")

    monkeypatch.setattr(cli, "fetch_transcript", failing)
    out = tmp_path / "n.md"

    assert cli.main([URL, "-o", str(out)]) == 1
    assert "error: SUPADATA_API_KEY is not set." in capsys.readouterr().err
    assert not out.exists()

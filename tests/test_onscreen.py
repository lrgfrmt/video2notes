import subprocess
from pathlib import Path

import pytest

from video2notes import onscreen as osc


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def tsv(*rows):
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    body = [
        f"5\t1\t{block}\t1\t{line}\t{n}\t0\t0\t10\t10\t{conf}\t{word}"
        for n, (block, line, conf, word) in enumerate(rows, start=1)
    ]
    return "\n".join([header, "1\t1\t0\t0\t0\t0\t0\t0\t640\t360\t-1\t", *body])


def test_keyframe_filter_combines_scene_changes_and_a_time_floor():
    vf = osc.keyframe_filter()

    assert "gt(scene,0.3)" in vf
    assert "gte(t-prev_selected_t,2.0)" in vf
    assert "isnan(prev_selected_t)" in vf
    assert vf.startswith("select='") and vf.endswith(",showinfo")


def test_parse_showinfo_reads_timestamps_in_order():
    stderr = "\n".join([
        "[Parsed_showinfo_1 @ 0x1] n:   0 pts:      0 pts_time:0       duration:1",
        "some other ffmpeg line pts_time:99",
        "[Parsed_showinfo_1 @ 0x1] n:   1 pts:  25600 pts_time:2.04    duration:1",
        "[Parsed_showinfo_1 @ 0x1] n:   2 pts:  51200 pts_time:13.12   duration:1",
    ])

    assert osc.parse_showinfo(stderr) == [0.0, 2.04, 13.12]


def test_extract_keyframes_pairs_frames_with_timestamps(tmp_path):
    calls = []

    def fake_ffmpeg(cmd):
        calls.append(cmd)
        out = Path(cmd[-1]).parent
        for i in (1, 2):
            (out / f"frame_{i:05d}.png").write_bytes(b"png")
        return completed(stderr="[Parsed_showinfo_1 @ 0] n:0 pts_time:0\n[Parsed_showinfo_1 @ 0] n:1 pts_time:4.5")

    frames = osc.extract_keyframes(tmp_path / "video.mp4", tmp_path / "frames", run=fake_ffmpeg)

    assert [f.start for f in frames] == [0.0, 4.5]
    assert [f.path.name for f in frames] == ["frame_00001.png", "frame_00002.png"]
    assert calls[0][0] == "ffmpeg" and "-vf" in calls[0]


def test_extract_keyframes_raises_when_ffmpeg_fails(tmp_path):
    with pytest.raises(osc.OnScreenError, match="ffmpeg failed"):
        osc.extract_keyframes(tmp_path / "v.mp4", tmp_path / "f", run=lambda cmd: completed(stderr="boom", returncode=1))


def test_parse_tsv_keeps_confident_lines_only():
    output = tsv(
        (1, 1, 96, "Install"), (1, 1, 91, "the"), (1, 1, 94, "CLI"),
        (1, 2, 20, "iA"), (1, 2, 31, "ail"),
        (2, 1, 88, "pip"), (2, 1, 85, "install"), (2, 1, 90, "video2notes"),
    )

    assert osc.parse_tsv(output) == ["Install the CLI", "pip install video2notes"]


@pytest.mark.parametrize("raw, expected", [
    ("  Hello   world  ", "Hello world"),
    ("pip install video2notes", "pip install video2notes"),
    ("ab", None),
    ("~~ | ~~", None),
    ("1 2 3 4", None),
])
def test_clean_line(raw, expected):
    assert osc.clean_line(raw) == expected


def test_dedupe_keeps_first_sighting_and_drops_near_copies():
    lines = [
        osc.OnScreenLine(4.0, "Subscribe for more"),
        osc.OnScreenLine(0.0, "Step 1: install the CLI"),
        osc.OnScreenLine(2.0, "Step 1 install the CLl"),  # OCR misread of the same caption
        osc.OnScreenLine(6.0, "install the CLI"),  # partial read during a transition
        osc.OnScreenLine(8.0, "Step 2: run it"),
    ]

    kept = osc.dedupe(lines)

    assert [(line.start, line.text) for line in kept] == [
        (0.0, "Step 1: install the CLI"),
        (4.0, "Subscribe for more"),
        (8.0, "Step 2: run it"),
    ]


def test_text_from_frames_runs_ocr_per_frame_and_dedupes(tmp_path):
    frames = [osc.Frame(0.0, tmp_path / "a.png"), osc.Frame(2.0, tmp_path / "b.png")]
    pages = {
        "a.png": tsv((1, 1, 95, "Hello"), (1, 1, 95, "there")),
        "b.png": tsv((1, 1, 95, "Hello"), (1, 1, 95, "there"), (2, 1, 92, "New"), (2, 1, 92, "slide")),
    }

    def fake_tesseract(cmd):
        assert cmd[0] == "tesseract" and cmd[-1] == "tsv"
        return completed(stdout=pages[Path(cmd[1]).name])

    lines = osc.text_from_frames(frames, run=fake_tesseract)

    assert [(line.start, line.text) for line in lines] == [(0.0, "Hello there"), (2.0, "New slide")]


def test_require_tools_names_what_is_missing(monkeypatch):
    monkeypatch.setattr(osc.shutil, "which", lambda name: None if name == "tesseract" else "/usr/bin/" + name)

    with pytest.raises(osc.OnScreenError, match="tesseract"):
        osc.require_tools()

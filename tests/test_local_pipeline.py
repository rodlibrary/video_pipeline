"""End-to-end tests for running the pipeline locally (no MPI, no SLURM).

Whisper inference is stubbed (see tests/support/sitecustomize.py) and the AI
steps talk to a fake OpenAI-compatible server, so no model downloads or API
keys are needed. ffmpeg/ffprobe must be installed.
"""

import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(REPO, "pipeline")
SUPPORT = os.path.join(REPO, "tests", "support")
sys.path.insert(0, PIPELINE)
sys.path.insert(0, SUPPORT)

from fake_llm_server import start_server  # noqa: E402
from pipeline_common import SerialComm, get_comm  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)

AI_SECTIONS = ["frame_descriptions", "summarization", "tagging", "accessibility", "collection_reports", "clustering"]
ALL_SECTIONS = AI_SECTIONS + ["keyframes", "preview_dashboard", "iiif", "quality_control", "catalog_export",
                              "search_index"]


def run_pipeline(project, *args, extra_env=None):
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    env.pop("OPENAI_BASE_URL", None)
    env["PYTHONPATH"] = SUPPORT
    env["AV_TEST_FAKE_WHISPER"] = "1"
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    env["NO_COLOR"] = "1"
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, os.path.join(PIPELINE, "run_pipeline.py"), "--config", "config.yaml", *args],
        cwd=project, env=env, capture_output=True, text=True, timeout=600,
    )


def make_media(media_dir):
    os.makedirs(os.path.join(media_dir, "sub"), exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=20:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        os.path.join(media_dir, "clip.mp4"),
    ], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=12",
        os.path.join(media_dir, "sub", "talk.mp3"),
    ], check=True)


def write_config(project, base_url, enable_all=True):
    with open(os.path.join(REPO, "local", "config.example.yaml"), encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    cfg["transcription"]["model"] = "tiny"
    cfg["keyframes"]["interval_seconds"] = 5.0
    if enable_all:
        for section in ALL_SECTIONS:
            cfg[section]["enabled"] = True
    for section in AI_SECTIONS:
        cfg[section]["base_url"] = base_url
        cfg[section]["model"] = "test-model"
    cfg["clustering"]["n_clusters"] = 3
    with open(os.path.join(project, "config.yaml"), "w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)
    return cfg


@pytest.fixture()
def llm_server():
    server, base_url, calls = start_server()
    yield base_url, calls
    server.shutdown()


def test_serial_comm_without_launcher(monkeypatch):
    for var in ("OMPI_COMM_WORLD_SIZE", "PMI_SIZE", "PMIX_RANK", "MPI_LOCALNRANKS"):
        monkeypatch.delenv(var, raising=False)
    comm = get_comm()
    assert isinstance(comm, SerialComm)
    assert comm.Get_rank() == 0 and comm.Get_size() == 1
    assert comm.bcast({"a": 1}) == {"a": 1}
    assert comm.gather(5) == [5]


@needs_ffmpeg
def test_full_local_pipeline(tmp_path, llm_server):
    base_url, calls = llm_server
    project = str(tmp_path)
    make_media(os.path.join(project, "media"))
    write_config(project, base_url)

    result = run_pipeline(project)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]

    out = os.path.join(project, "output")
    # Transcription: nested file names are flattened with "__".
    for stem in ("clip", "sub__talk"):
        for fmt in ("txt", "srt", "json", "tsv"):
            assert os.path.exists(os.path.join(out, "transcripts", fmt, f"{stem}.{fmt}"))

    # Keyframes: video gets frames, audio-only file is skipped (not an error).
    interval_frames = os.listdir(os.path.join(out, "keyframes", "interval"))
    speech_frames = os.listdir(os.path.join(out, "keyframes", "speech_segments"))
    assert interval_frames and all(f.startswith("clip_t") for f in interval_frames)
    assert speech_frames and all(f.startswith("clip_t") for f in speech_frames)
    assert "encountered errors" not in result.stderr, result.stderr[-3000:]

    # AI steps went through the local base_url, including an image request and JSON mode.
    paths = [p for p, _ in calls]
    assert any(p.endswith("/chat/completions") for p in paths)
    assert any(p.endswith("/embeddings") for p in paths)
    assert any(isinstance(b.get("messages", [{}])[-1].get("content"), list) for _, b in calls)
    assert any(b.get("response_format") == {"type": "json_object"} for _, b in calls)

    descs = []
    for root, _, files in os.walk(os.path.join(out, "frame_descriptions")):
        descs += [f for f in files if f.endswith(".txt")]
    assert len(descs) == len(set(interval_frames) | set(speech_frames))

    assert sorted(os.listdir(os.path.join(out, "summaries"))) == ["clip.txt", "sub__talk.txt"]
    with open(os.path.join(out, "tags", "clip.json"), encoding="utf-8") as handle:
        assert json.load(handle)["topics"] == ["testing"]
    assert sorted(os.listdir(os.path.join(out, "accessibility_notes"))) == ["clip.txt", "sub__talk.txt"]
    assert os.path.getsize(os.path.join(out, "collection_report.md")) > 0
    assert os.path.exists(os.path.join(out, "preview", "index.html"))
    with open(os.path.join(out, "iiif", "manifest.json"), encoding="utf-8") as handle:
        assert json.load(handle)
    with open(os.path.join(out, "clusters", "clusters.json"), encoding="utf-8") as handle:
        assert json.load(handle)["n_clusters"] >= 2

    # Downstream exports now find transcripts (previously looked up a key that never existed).
    with open(os.path.join(out, "quality_metrics.csv"), encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {r["id"] for r in rows} == {"clip", "sub__talk"}
    assert all(float(r["transcript_word_count"]) > 0 for r in rows)
    with open(os.path.join(out, "catalog_export.csv"), encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2 and all("Segment 1" in r["TranscriptExcerpt"] for r in rows)
    con = sqlite3.connect(os.path.join(out, "search_index.db"))
    assert con.execute("SELECT count(*) FROM documents WHERE documents MATCH 'transcript:recording'").fetchone()[0] == 2
    con.close()

    with open(os.path.join(out, "provenance_log.jsonl"), encoding="utf-8") as handle:
        record = json.loads(handle.readlines()[-1])
    assert record["success"] is True and record["mode"] == "local"
    assert [s["step"] for s in record["steps"]] == [
        "transcribe", "keyframes", "describe_frames", "summarize", "tags", "accessibility",
        "collection_report", "preview", "quality_metrics", "iiif", "catalog_export",
        "search_index", "clustering",
    ]

    # Re-running is safe: existing per-item outputs are skipped, nothing fails.
    n_calls = len(calls)
    rerun = run_pipeline(project, "--steps", "transcribe", "keyframes", "describe_frames", "summarize", "tags")
    assert rerun.returncode == 0, rerun.stdout[-3000:] + rerun.stderr[-3000:]
    assert len(calls) == n_calls


@needs_ffmpeg
def test_disabled_steps_are_skipped_and_list_works(tmp_path, llm_server):
    base_url, _ = llm_server
    project = str(tmp_path)
    make_media(os.path.join(project, "media"))
    write_config(project, base_url, enable_all=False)

    listing = run_pipeline(project, "--list")
    assert listing.returncode == 0
    assert "summarize" in listing.stdout and "summarization.enabled" in listing.stdout

    result = run_pipeline(project, "--steps", "transcribe", "summarize")
    assert result.returncode == 0, result.stderr
    assert "Skipping 'summarize'" in result.stdout
    assert os.path.exists(os.path.join(project, "output", "transcripts", "txt", "clip.txt"))


def test_preflight_reports_missing_api_key(tmp_path):
    project = str(tmp_path)
    os.makedirs(os.path.join(project, "media"))
    cfg = write_config(project, base_url=None)
    cfg["summarization"]["base_url"] = None
    with open(os.path.join(project, "config.yaml"), "w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)

    result = run_pipeline(project, "--steps", "summarize", "--check")
    assert result.returncode != 0
    assert "OPENAI_API_KEY" in result.stderr


def test_unknown_step_is_rejected(tmp_path):
    project = str(tmp_path)
    write_config(project, base_url="http://127.0.0.1:9/v1")
    result = run_pipeline(project, "--steps", "transcribee")
    assert result.returncode != 0 and "Unknown step" in result.stderr

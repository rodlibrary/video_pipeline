"""Test-only hook: when AV_TEST_FAKE_WHISPER=1, replace Whisper inference with a stub.

Python imports ``sitecustomize`` automatically when this folder is on
PYTHONPATH, so every pipeline stage started by run_pipeline.py picks it up.
Audio is still decoded for real with Whisper's ffmpeg loader, so media
handling is exercised; only the neural network is skipped (no model download).
"""

import os

if os.environ.get("AV_TEST_FAKE_WHISPER") == "1":
    try:
        import whisper
    except ImportError:  # pragma: no cover - whisper not installed
        whisper = None

    if whisper is not None:

        class _FakeModel:
            def transcribe(self, path, **_kwargs):
                audio = whisper.load_audio(path)  # real ffmpeg decode, 16 kHz mono
                duration = len(audio) / 16000.0
                segments = []
                start, idx = 0.0, 0
                while start < duration:
                    end = min(start + 5.0, duration)
                    segments.append({
                        "id": idx, "seek": 0, "start": start, "end": end,
                        "text": f" Segment {idx + 1} of the test recording.",
                        "tokens": [], "temperature": 0.0, "avg_logprob": 0.0,
                        "compression_ratio": 1.0, "no_speech_prob": 0.0,
                    })
                    start, idx = end, idx + 1
                return {
                    "text": "".join(s["text"] for s in segments),
                    "segments": segments,
                    "language": "en",
                    "duration": duration,
                }

        def _fake_load_model(name, *args, **kwargs):
            return _FakeModel()

        whisper.load_model = _fake_load_model

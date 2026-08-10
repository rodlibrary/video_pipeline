# Parallel AV Transcription Toolkit

A high performance cluster configured and MPI-friendly transcription workflow designed for digital librarians, archivists, curators, and developers who manage large audiovisual collections. The toolkit builds on `https://github.com/mbutler/archive_to_access` 

## What this provides
- **Parallel transcription**: Scan large audio/video collections (optional recursion) and distribute work across MPI ranks.
- **Optional audio normalization** keeps legacy formats consistent for WhisperX ingestion.
- **Parallel transcription** outputs `txt`, `json`, `tsv`, or `srt`.
- **Keyframe extraction + Gemini** produces storyboard descriptions of visual content.
- **Summaries, tags, & accessibility notes** provide layered AI metadata (text + visuals + narration cues).
- **Collection analytics**: generate research briefings, quality reports, clustering insights, and IIIF manifests.
- **Discovery outputs**: export catalog-ready CSV, SQLite FTS index, HTML preview dashboard.
- **Workflow automation**: `submit_pipeline.py` sequences steps with provenance logs.

## Steps
1. **Install dependencies**

  * mpi4py>=3.1
  * whisperx (requires Hugging Face token)
  * PyYAML>=6.0
  * numpy>=1.24
  * google-genai (requires API Key and tokens)
  * scikit-learn>=1.3
  * jinja2>=3.1
  * pandas>=1.5

2. **Unzip `av_pipeline_slurm_chain.zip` alongside `run_pipeline.py` and `config.yaml`**

Contents:
* `common_env.sh`              # shared module loads, env activation, GOOGLE_API_KEY loading — sourced by every stage
* `01_transcribe.slurm`        # GPU, 2 nodes x 1 task (one Whisper instance per GPU)
* `02_keyframes.slurm`         # CPU, 4 nodes x 16 tasks (ffmpeg fans out cheaply)
* `03_describe_frames.slurm`   # CPU, 2 nodes x 4 tasks (Gemini Vision — kept modest for rate limits)
* `04_summarize.slurm`         # CPU, 1 node x 8 tasks (Gemini text)
* `05_tags.slurm`              # CPU, 1 node x 8 tasks (Gemini text)
* `06_accessibility.slurm`     # CPU, 1 node x 8 tasks (Gemini text)
* `07_collection_report.slurm` # single task — not rank-aware
* `08_preview.slurm`          # single task — no API calls
* `09_quality_metrics.slurm`   # single task — no API calls
* `10_iiif.slurm`              # single task — no API calls
* `11_catalog_export.slurm`    # single task — no API calls
* `12_search_index.slurm`      # single task — no API calls
* `13_clustering.slurm`        # single task — Gemini embeddings, batched internally
* `submit_pipeline.sh`         # driver: submits the chain with --dependency=afterok

Configuration Overview

The YAML file controls several areas:

| Section | Purpose |
| ------- | ------- |
| `input` | Where to find media, which extensions to include, and whether to search subdirectories. |
| `preprocessing` | Optional audio extraction/normalization details. Disable if your media is already Whisper-ready. |
| `transcription` | Whisper model choice, device, language hints, and decoding parameters. |
| `outputs` | Top-level folder, output formats, and writer options shared across formats. |
| `keyframes` | Optional still-frame extraction settings (modes, intervals, segment parsing, output layout). |
| `frame_descriptions` | Optional Gemini settings to describe frames, with transcript and metadata context. |
| `summarization` | Gemini summarization settings, including use of frame descriptions. |
| `tagging` | Gemini-based entity and topic tagging of transcripts. |
| `collection_reports` | Collection-wide synthesis reports. |
| `accessibility` | Audio-description narration cues based on transcripts/frames. |
| `preview_dashboard` | Static HTML preview builder. |
| `quality_control` | Heuristic metrics and flags for QA triage. |
| `iiif` | IIIF manifest generation parameters. |
| `catalog_export` | CSV export options for library systems. |
| `search_index` | SQLite full-text index settings. |
| `clustering` | Visual theme clustering (text embeddings + k-means). |
| `workflow` | Ordered pipeline steps for `run_pipeline.py`. |
| `logging` | Verbosity controls and how often to print progress. |

**3. Orchestrate everything**

`chmod +x slurm/*.sh slurm/*.slurm`

`./slurm/submit_pipeline.sh config.yaml`

Each stage only runs after the previous one exits successfully (afterok), and each requests its own resources — GPU for transcription, wide CPU fan-out for ffmpeg, dialed-back concurrency for the Gemini API steps — instead of one job sized for the whole workflow.

Two extras built into the driver:

* Skip stages you've already run: `SKIP_STEPS="transcribe keyframes" ./slurm/submit_pipeline.sh config.yaml`
* Run only a subset: `ONLY_STEPS="describe_frames summarize" ./slurm/submit_pipeline.sh config.yaml`

A few things to tune for your actual cluster before submitting:

* Partition names (`gpu`, `compute`) and module names in `common_env.sh` and each stage file are placeholders.
*Per-stage `--nodes`/`--ntasks-per-node` are starting points — the Gemini API steps in particular should be tuned down if you hit rate limits, and `describe_frames/keyframes` sized up if your collection is large.
* `transcription.device: "cuda"` needs to be set in `config.yaml` for the GPU request in `01_transcribe.slurm` to actually get used.

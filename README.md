# AV Pipeline Toolkit — local edition

A transcription and AI-description workflow for digital librarians, archivists, curators, and developers who manage audiovisual collections. Point it at a folder of video/audio files and it produces transcripts, keyframes, optional AI summaries/tags/accessibility notes, and discovery outputs (HTML preview, IIIF manifest, catalog CSV, SQLite search index).

This edition runs on an ordinary computer from the terminal: no MPI, no SLURM, no cluster. (It builds on `https://github.com/mbutler/archive_to_access`. Cluster users can still use MPI, see [Running on a cluster](#running-on-a-cluster).)

## What it produces

| Step | What it does | Needs |
| ---- | ------------ | ----- |
| `transcribe` | Whisper speech-to-text → `txt`, `srt`, `json`, `tsv` | ffmpeg |
| `keyframes` | Still frames at intervals and at the middle of each speech segment | ffmpeg |
| `describe_frames` | Vision-model description of each frame | AI model |
| `summarize` | Short summary per item (transcript + frame descriptions) | AI model |
| `tags` | Entities, topics, keywords as JSON | AI model |
| `accessibility` | Audio-description style narration cues | AI model |
| `collection_report` | One briefing across the whole collection | AI model |
| `preview` | Static HTML dashboard | — |
| `quality_metrics` | QA metrics/flags CSV | summaries |
| `iiif` | IIIF manifest for the keyframes | — |
| `catalog_export` | Catalog-ready CSV | summaries |
| `search_index` | SQLite full-text index | summaries |
| `clustering` | Groups frames into visual themes (embeddings + k-means) | AI model |

## Quick start

**1. Install ffmpeg** (used to read media and grab frames)

```bash
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian/Ubuntu
winget install ffmpeg        # Windows
```

**2. Install the Python packages** (Python 3.9+; a virtual environment is recommended)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`openai-whisper` pulls in PyTorch, so the first install takes a few minutes. Whisper downloads its model weights automatically the first time it runs.

**3. Make a config and add media**

```bash
cp config-local.yaml config.yaml
mkdir media                        # put your .mp4/.mov/.mp3/... files here (subfolders are fine)
```

Or set `input.media_root` in `config.yaml` to an existing folder.

**4. Run it**

```bash
python run_pipeline.py --list      # see which steps are enabled
python run_pipeline.py --check     # check ffmpeg, packages, API keys, media folder
python run_pipeline.py             # run all enabled steps
```

Results go to `output/`. Open `output/preview/index.html` in a browser when it finishes.

Out of the box, `config-local.yaml` runs the steps that need no API key: **transcribe → keyframes → preview → iiif**.

## Turning on the AI steps

The AI steps talk to any OpenAI-compatible API. Pick one:

**OpenAI**

```bash
export OPENAI_API_KEY=sk-...       # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."
```

**A local model, fully offline** (e.g. [Ollama](https://ollama.com))

```bash
ollama pull llama3.1 && ollama pull llava && ollama pull nomic-embed-text
export OPENAI_BASE_URL=http://localhost:11434/v1
```

Then set models in the config: `llava` for `frame_descriptions`, `llama3.1` for the text steps, `nomic-embed-text` for `clustering`. LM Studio works the same way (`http://localhost:1234/v1`). If a local model rejects JSON mode, set `tagging.json_mode: false`.

**Google Gemini** (via its OpenAI-compatible endpoint): on each AI section set `base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"`, `api_key_env: "GOOGLE_API_KEY"`, and a Gemini model name.

Then set `enabled: true` on the sections you want: `frame_descriptions`, `summarization`, `tagging`, `accessibility`, `collection_reports`, `clustering`. Turn on `quality_control`, `catalog_export` and `search_index` together with `summarization`, since they read the summaries.

## Running parts of the pipeline

```bash
python run_pipeline.py --steps transcribe keyframes   # only these steps
python run_pipeline.py --skip transcribe              # everything else
python run_pipeline.py --keep-going                   # don't stop at the first failed step
python run_pipeline.py --dry-run                      # show what would run
python run_pipeline.py --config ~/projects/oral-history/config.yaml
```

Every step is also a standalone script, e.g. `python transcribe_collection.py --config config.yaml`.

**Re-running is safe.** Each step skips items it has already produced, so you can stop with Ctrl-C and resume, or add new files to `media/` and run again. Set `overwrite: true` in a section to redo its outputs.

**Paths.** Relative paths in the config are resolved against the folder containing the config file, so you can run the pipeline from anywhere.

**Provenance.** Each run appends a JSON record (steps, commands, timings, exit codes) to `output/provenance_log.jsonl`.

## Choosing a Whisper model

| Model | Speed on a laptop CPU | Accuracy |
| ----- | --------------------- | -------- |
| `tiny`, `base` | fast | fine for clear speech; good for a first run |
| `small`, `medium` | slower | noticeably better on difficult audio |
| `large-v3` | slow without a GPU | best |

With an NVIDIA GPU, set `transcription.device: "cuda"` and use `large-v3`. Set `transcription.language` (e.g. `"en"`) if you know it.

## Configuration overview

| Section | Purpose |
| ------- | ------- |
| `input` | Media folder, file extensions, whether to scan subfolders. |
| `preprocessing` | Optional ffmpeg audio normalization before Whisper. |
| `transcription` | Whisper model, device, language, decoding options. |
| `outputs` | Transcript folder and formats. |
| `keyframes` | Frame sampling: intervals, speech-segment midpoints, caps. |
| `frame_descriptions`, `summarization`, `tagging`, `accessibility`, `collection_reports`, `clustering` | AI steps: `enabled`, `model`, `api_key_env`, `base_url`, prompts. |
| `preview_dashboard`, `quality_control`, `iiif`, `catalog_export`, `search_index` | Output builders. |
| `workflow` | Step order for `run_pipeline.py`. |
| `provenance`, `logging` | Run log location; verbosity and progress output. |

Optional item metadata (e.g. title, date) can be supplied as a CSV via `metadata_csv`; rows are matched to files by name (nested paths become `folder__file`).

`config-example.yaml` and `config-gold-standard.yaml` are the original, fuller examples.

## Tests

```bash
pip install pytest
pytest
```

The tests run the whole pipeline on a generated clip with Whisper inference stubbed and a fake OpenAI-compatible server, so they need ffmpeg but no model downloads or API keys.

## Running on a cluster

The stages are still MPI-aware. When launched under `mpirun`/`srun` with `mpi4py` installed, they split work across ranks; otherwise they run as a single process.

```bash
pip install mpi4py
python run_pipeline.py --mpi --ranks 8
```

`av_pipeline_slurm_chain.zip` contains the original SLURM job chain (one job per step, chained with `--dependency=afterok`). Unzip it into a `slurm/` folder and run `./slurm/submit_pipeline.sh config.yaml`; adjust partitions, module names and the API key variable in `common_env.sh` for your cluster.

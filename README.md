# AV Pipeline Toolkit

A transcription and AI-description workflow for digital librarians, archivists, curators, and developers who manage audiovisual collections. Point it at a folder of video and audio files and it produces transcripts, keyframes, optional AI summaries, tags and accessibility notes, and discovery outputs: an HTML preview, a IIIF manifest, a catalog CSV and a SQLite search index.

The toolkit builds on `https://github.com/mbutler/archive_to_access`.

## Choose how to run it

| | [**Local**](local/README.md) | [**Cluster**](cluster/README.md) |
| --- | --- | --- |
| Runs on | Your laptop or workstation, from a terminal | An HPC cluster with SLURM and MPI |
| Parallelism | One process, step by step | Each step is its own SLURM job, fanned out over MPI ranks |
| Good for | Trying it out, small to medium collections | Large collections, GPU transcription |
| Start with | `local/config.example.yaml` | `cluster/config.example.yaml` + `cluster/slurm/` |

Both options run the same code in [`pipeline/`](pipeline/README.md); only the configuration and the way steps are launched differ.

## Repository layout

```
pipeline/     The pipeline: one script per step, plus run_pipeline.py to run them in order
local/        Config template and instructions for running on one machine
cluster/      Config templates, SLURM job scripts and instructions for HPC clusters
tests/        End-to-end tests (no model downloads or API keys needed)
requirements.txt
```

## Pipeline steps

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
| `quality_metrics` | QA metrics and flags CSV | summaries |
| `iiif` | IIIF manifest for the keyframes | — |
| `catalog_export` | Catalog-ready CSV | summaries |
| `search_index` | SQLite full-text index | summaries |
| `clustering` | Groups frames into visual themes (embeddings + k-means) | AI model |

The AI steps work with OpenAI, with a local model server such as Ollama or LM Studio (fully offline), or with Google Gemini through its OpenAI-compatible endpoint.

## Quick start (local)

```bash
pip install -r requirements.txt                  # plus ffmpeg from your package manager
cp local/config.example.yaml local/config.yaml
mkdir local/media                                # add your video/audio files here
python pipeline/run_pipeline.py
```

See [local/README.md](local/README.md) for details, and [cluster/README.md](cluster/README.md) for SLURM.

## Tests

```bash
pip install pytest
pytest
```

The tests run the whole pipeline on a generated clip with Whisper inference stubbed and a fake OpenAI-compatible server, so they need ffmpeg but no model downloads or API keys.

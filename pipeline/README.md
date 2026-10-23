# Pipeline code

The scripts here are shared by the [local](../local/README.md) and [cluster](../cluster/README.md) options.

| Script | Step |
| ------ | ---- |
| `run_pipeline.py` | Runs the enabled steps in order and logs provenance |
| `transcribe_collection.py` | `transcribe` |
| `extract_keyframes.py` | `keyframes` |
| `describe_frames.py` | `describe_frames` |
| `summarize_collection.py` | `summarize` |
| `generate_tags.py` | `tags` |
| `generate_accessibility.py` | `accessibility` |
| `collection_report.py` | `collection_report` |
| `build_preview.py` | `preview` |
| `quality_metrics.py` | `quality_metrics` |
| `build_iiif_manifest.py` | `iiif` |
| `export_catalog.py` | `catalog_export` |
| `build_search_index.py` | `search_index` |
| `cluster_visuals.py` | `clustering` |
| `pipeline_common.py` | Shared helpers: optional MPI, OpenAI-compatible client |
| `configure_tool.py` | Interactive wizard that writes a config file |

Every step script also runs on its own, e.g. `python pipeline/transcribe_collection.py --config local/config.yaml`. Run step scripts from the config file's folder (or use `run_pipeline.py`, which does this for you), because relative paths in the config resolve against the working directory.

## Parallelism

`transcribe`, `keyframes`, `describe_frames`, `summarize`, `tags` and `accessibility` are MPI-aware. When started under `mpirun`/`srun` with `mpi4py` installed, they split their files across ranks; otherwise they run as a single process. The other steps are always single-process.

`run_pipeline.py` runs steps locally by default, uses `mpirun` with `--mpi --ranks N`, and uses `mpirun` automatically inside a SLURM job (disable with `--no-mpi`).

## Configuration reference

| Section | Purpose |
| ------- | ------- |
| `input` | Media folder, file extensions, whether to scan subfolders. |
| `preprocessing` | Optional ffmpeg audio normalization before Whisper. |
| `transcription` | Whisper model, device, language, decoding options. |
| `outputs` | Transcript folder and formats. |
| `keyframes` | Frame sampling: intervals, speech-segment midpoints, caps. Audio-only files are skipped. |
| `frame_descriptions`, `summarization`, `tagging`, `accessibility`, `collection_reports`, `clustering` | AI steps: `enabled`, `model`, `api_key_env`, `base_url`, prompts, output folders. |
| `preview_dashboard`, `quality_control`, `iiif`, `catalog_export`, `search_index` | Output builders. |
| `workflow.steps` | Step order for `run_pipeline.py`. Disabled steps are skipped. |
| `provenance` | Where run records are appended. |
| `logging` | Per-file error output and progress frequency. |

Each AI section accepts `base_url` to use an OpenAI-compatible server other than OpenAI (Ollama, LM Studio, Gemini); the `OPENAI_BASE_URL` environment variable sets it for all sections at once. When `base_url` points at a local server, no API key is needed.

Output names come from the media file name without extension; files in subfolders become `folder__file`. A step skips items whose outputs already exist unless that section has `overwrite: true`.

# Parallel AV Transcription Toolkit

An HPC-friendly transcription workflow utilizing SLURM and Gemini designed for digital librarians, archivists, curators, and developers who manage large audiovisual collections. The toolkit builds on `https://github.com/BreuerLabs/AI-SummarizeVid` 

## What This Provides
- **Parallel transcription**: Scan large audio/video collections (optional recursion) and distribute work across MPI ranks.
- **Optional audio normalization** keeps legacy formats consistent for Whisper ingestion.
- **Parallel transcription** outputs `txt`, `json`, `tsv`, or `srt`.
- **Keyframe extraction + Gemini** produces storyboard descriptions of visual content.
- **Summaries, tags, & accessibility notes** provide layered AI metadata (text + visuals + narration cues).
- **Collection analytics**: generate research briefings, quality reports, clustering insights, and IIIF manifests.
- **Discovery outputs**: export catalog-ready CSV, SQLite FTS index, HTML preview dashboard.
- **Workflow automation**: `run_pipeline.py` sequences steps with provenance logs; `configure_tool.py` bootstraps configs interactively.

## Quick Start
1. **Install prerequisites**
   ```bash
   brew install ffmpeg open-mpi        # macOS example
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Unzip av_pipeline_slurm_chain.zip** alongside run_pipeline.py and config.yaml

4. **Prepare a configuration**

   # edit config.yaml so the paths match your collection and desired outputs
   ```
3. **Launch a transcription run**

    ```SLURM
  sbatch submit_pipeline.sh config.yaml
   ```
```chmod +x slurm/*.sh slurm/*.slurm
./slurm/submit_pipeline.sh config.yaml
   ```
4. **Notes**
   Partition names (gpu, compute) and module names in common_env.sh and each stage file are placeholders.
Per-stage --nodes/--ntasks-per-node are starting points — the Gemini API steps in particular should be tuned down if you hit rate limits, and describe_frames/keyframes sized up if your collection is large.
transcription.device: "cuda" needs to be set in config.yaml for the GPU request in 01_transcribe.slurm to actually get used.


## Configuration Overview
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


The preset writes transcripts, keyframes, Gemini frame descriptions, and Gemini summaries into `outputs/transcripts_gold`, `outputs/keyframes_gold`, `outputs/frame_descriptions_gold`, and `outputs/summaries_gold`, and it enforces 3-second interval sampling (capped at 60 frames) with the published prompt language to ensure behavioral parity.

## Optional Audio Normalization
`ffmpeg` preprocessing is helpful when collections contain a patchwork of legacy formats—normalizing sample rate, channel layout, and codecs improves transcription consistency and avoids Whisper’s fallback re-encoding. If your collection is already stored as modern MP4/MKV with AAC stereo audio, you can disable preprocessing to skip that extra I/O.

## Keyframes & Vision Descriptions
- Enable the `keyframes` section to sample stills at regular intervals, per speech segment, or both. Outputs live under `keyframes/<mode>/...`.
- Turn on `frame_descriptions` to send each still to a vision-capable Gemini model. Prompts can include transcript excerpts and metadata for richer, neutral descriptions.
- Descriptions mirror the keyframe directory tree, allowing easy correlation between images and text.

## Multi-Layer Outputs
- Configure `summarization` to feed transcripts (and optionally frame descriptions) into concise Gemini outputs.
- Enable `tagging`, `collection_reports`, `accessibility`, and `quality_control` to produce structured metadata, narrations, and QA dashboards.
- `build_preview.py` assembles a static HTML gallery (with optional custom CSS) for quick inspection.
- `build_iiif_manifest.py` and `export_catalog.py` prepare assets for IIIF viewers and standard catalog systems.
- `build_search_index.py` creates a SQLite FTS database that you can query with SQL or wrap in a simple API.
- `cluster_visuals.py` uses OpenAI embeddings + k-means to group similar frame descriptions, helping surface recurring visuals.
- `run_pipeline.py` ties it all together with provenance logging; `configure_tool.py` lets new users bootstrap configs interactively.

## Output Layout
The script creates (and reuses) subdirectories inside `outputs.base_dir`, one per requested format:

```
transcripts/
  txt/
  srt/
  json/
  tsv/
```

Filenames mirror the relative path of each media asset with directory separators replaced by `__`. This keeps outputs unique, even when the source collection contains identical filenames in different folders.

## Scaling Tips
- MPI scaling is roughly linear up to saturated disk or network throughput; use `np.array_split` across ranks to balance workloads.
- Use `mpirun -np <N> ...` on a single machine for light collections or distribute across cluster nodes if your environment provides a shared filesystem.
- Whisper models are GPU-accelerated when `device` is set to `cuda` and a compatible GPU is available; otherwise they run on CPU.

## Extending the Workflow
- Swap Whisper model sizes (`base`, `small`, `medium`, `large-v3`) in the config to balance quality and runtime.
- Feed the generated transcripts into your own discovery interfaces or cataloging systems.
- Enable the gold-standard preset when you want the full storyboard + summary flow from the published AI-SummarizeVid workflow.


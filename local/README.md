# Running locally

Run the pipeline on one computer from a terminal: no MPI, no SLURM. Steps run one after another in a single process each. Commands below are run from the repository root.

## 1. Install

**ffmpeg** (reads media and extracts frames):

```bash
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian/Ubuntu
winget install ffmpeg        # Windows
```

**Python packages** (Python 3.9+; a virtual environment is recommended):

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`openai-whisper` pulls in PyTorch, so the first install takes a few minutes. Whisper downloads its model weights automatically the first time it runs.

## 2. Configure

```bash
cp local/config.example.yaml local/config.yaml
mkdir local/media                  # put your .mp4/.mov/.mp3/... files here (subfolders are fine)
```

Or set `input.media_root` in `local/config.yaml` to an existing folder. Relative paths in the config are resolved against the `local/` folder, so results go to `local/output/`.

## 3. Run

```bash
python pipeline/run_pipeline.py --list      # which steps are enabled
python pipeline/run_pipeline.py --check     # check ffmpeg, packages, API keys, media folder
python pipeline/run_pipeline.py             # run all enabled steps
```

Without `--config`, the runner uses `./config.yaml` if there is one in the current folder, otherwise `local/config.yaml`.

Out of the box the config runs the steps that need no API key: **transcribe → keyframes → preview → iiif**. Open `local/output/preview/index.html` in a browser when it finishes.

## Turning on the AI steps

The AI steps talk to any OpenAI-compatible API. Pick one:

**OpenAI**

```bash
export OPENAI_API_KEY=sk-...       # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."
```

**A local model, fully offline** (e.g. [Ollama](https://ollama.com)):

```bash
ollama pull llama3.1 && ollama pull llava && ollama pull nomic-embed-text
export OPENAI_BASE_URL=http://localhost:11434/v1
```

Then set models in the config: `llava` for `frame_descriptions`, `llama3.1` for the text steps, `nomic-embed-text` for `clustering`. LM Studio works the same way (`http://localhost:1234/v1`). If a local model rejects JSON mode, set `tagging.json_mode: false`.

**Google Gemini** (OpenAI-compatible endpoint): on each AI section set `base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"`, `api_key_env: "GOOGLE_API_KEY"`, and a Gemini model name.

Then set `enabled: true` on the sections you want: `frame_descriptions`, `summarization`, `tagging`, `accessibility`, `collection_reports`, `clustering`. Turn on `quality_control`, `catalog_export` and `search_index` together with `summarization`, since they read the summaries.

## Running parts of the pipeline

```bash
python pipeline/run_pipeline.py --steps transcribe keyframes   # only these steps
python pipeline/run_pipeline.py --skip transcribe              # everything else
python pipeline/run_pipeline.py --keep-going                   # don't stop at the first failed step
python pipeline/run_pipeline.py --dry-run                      # show what would run
python pipeline/run_pipeline.py --config ~/projects/oral-history/config.yaml
```

**Re-running is safe.** Each step skips items it has already produced, so you can stop with Ctrl-C and resume, or add new files and run again. Set `overwrite: true` in a section to redo its outputs.

**Provenance.** Each run appends a JSON record (steps, commands, timings, exit codes) to `local/output/provenance_log.jsonl`.

## Choosing a Whisper model

| Model | Speed on a laptop CPU | Accuracy |
| ----- | --------------------- | -------- |
| `tiny`, `base` | fast | fine for clear speech; good for a first run |
| `small`, `medium` | slower | noticeably better on difficult audio |
| `large-v3` | slow without a GPU | best |

The template uses `base`. With an NVIDIA GPU, set `transcription.device: "cuda"` and use `large-v3`. Set `transcription.language` (e.g. `"en"`) if you know it.

## Item metadata

Optional metadata (e.g. title, date) can be supplied as a CSV via `metadata_csv` in the AI sections. Rows are matched to files by name without extension; files in subfolders are named `folder__file`.

See [../pipeline/README.md](../pipeline/README.md) for the full configuration reference.

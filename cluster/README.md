# Running on an HPC cluster (SLURM + MPI)

Each pipeline step is submitted as its own SLURM job, chained with `--dependency=afterok` so a step only starts after the previous one succeeds. Each job requests its own resources: GPUs for transcription, wide CPU fan-out for ffmpeg, modest concurrency for the AI API steps. Within a job, the rank-aware steps split their files across MPI ranks.

```
cluster/
├── config.example.yaml        # template; copy to config.yaml
├── config-gold-standard.yaml  # fuller example inspired by AI-SummarizeVid
└── slurm/
    ├── common_env.sh              # module loads, environment activation, API keys — sourced by every job
    ├── submit_pipeline.sh         # submits the whole chain
    ├── 01_transcribe.slurm        # GPU, 2 nodes x 1 task (one Whisper instance per GPU)
    ├── 02_keyframes.slurm         # CPU, 4 nodes x 16 tasks (ffmpeg fans out cheaply)
    ├── 03_describe_frames.slurm   # CPU, 2 nodes x 4 tasks (vision API — modest for rate limits)
    ├── 04_summarize.slurm         # CPU, 1 node x 8 tasks (text API)
    ├── 05_tags.slurm              # CPU, 1 node x 8 tasks (text API)
    ├── 06_accessibility.slurm     # CPU, 1 node x 8 tasks (text API)
    ├── 07_collection_report.slurm # single task
    ├── 08_preview.slurm           # single task, no API calls
    ├── 09_quality_metrics.slurm   # single task, no API calls
    ├── 10_iiif.slurm              # single task, no API calls
    ├── 11_catalog_export.slurm    # single task, no API calls
    ├── 12_search_index.slurm      # single task, no API calls
    └── 13_clustering.slurm        # single task, embeddings batched internally
```

## 1. Set up the environment

On a login node, create an environment with the dependencies plus `mpi4py`, built against your cluster's MPI:

```bash
module load openmpi miniconda3        # names vary by cluster
conda create -n av-toolkit python=3.11 -y
source activate av-toolkit
pip install -r requirements.txt mpi4py
```

Then edit `cluster/slurm/common_env.sh` so its `module load` lines and environment activation match your cluster.

**API keys.** Store keys in files only you can read; `common_env.sh` exports them for every job:

```bash
mkdir -p ~/.secrets && chmod 700 ~/.secrets
echo "sk-..." > ~/.secrets/openai_api_key   # OpenAI (OPENAI_API_KEY)
echo "..."   > ~/.secrets/google_api_key    # Gemini (GOOGLE_API_KEY), if used
chmod 600 ~/.secrets/*
```

Which variable a step reads is set by `api_key_env` in its config section. To use Gemini, set on each AI section `base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"`, `api_key_env: "GOOGLE_API_KEY"`, and a Gemini model name. Steps that need no API (transcribe, keyframes, preview, IIIF) run without any key.

## 2. Configure

```bash
cp cluster/config.example.yaml cluster/config.yaml
```

- Set `input.media_root`, preferably to an absolute path on a shared filesystem.
- Set `transcription.device: "cuda"` so the GPU requested by `01_transcribe.slurm` is actually used.
- Set `enabled: true` on the steps you want. Disabled steps exit immediately inside their job without failing the chain; use `SKIP_STEPS` to avoid queueing them at all.
- Relative paths are resolved against the config file's folder (`cluster/`).

## 3. Tune the job scripts

Before submitting, review for your cluster:

- Partition names (`gpu`, `compute`) and module names are placeholders.
- `--nodes` / `--ntasks-per-node` per stage are starting points. Turn the AI steps down if you hit API rate limits; size up `keyframes` and `describe_frames` for large collections.
- `--time` and `--mem` per stage.

## 4. Submit

```bash
cluster/slurm/submit_pipeline.sh                      # uses cluster/config.yaml
cluster/slurm/submit_pipeline.sh path/to/other.yaml   # or another config
```

It works from any directory. Logs go to `cluster/logs/`. Track the chain with `squeue -u $USER`.

```bash
SKIP_STEPS="transcribe keyframes" cluster/slurm/submit_pipeline.sh        # already done
ONLY_STEPS="describe_frames summarize" cluster/slurm/submit_pipeline.sh   # just these
```

Each step skips items it already produced, so resubmitting after a failure picks up where it left off.

## How the jobs run the pipeline

Each job calls `pipeline/run_pipeline.py --steps <step>`. Inside a SLURM job the runner launches the step with `mpirun -np $SLURM_NTASKS`, and the step splits its files across ranks. Single-task steps pass `--no-mpi`.

You can also run the whole pipeline inside one allocation instead of the job chain:

```bash
salloc -N 2 --ntasks-per-node=8
python pipeline/run_pipeline.py --config cluster/config.yaml --mpi --ranks 16
```

Each step appends a provenance record (commands, timings, exit codes) to the log set by `provenance.log_path`.

See [../pipeline/README.md](../pipeline/README.md) for the full configuration reference.

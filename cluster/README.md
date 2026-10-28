# Running on an HPC cluster (SLURM + MPI)

Each pipeline step is submitted as its own SLURM job, chained with `--dependency=afterok` so a step only starts after the previous one succeeds. Each job requests its own resources: GPUs for transcription, wide CPU fan-out for ffmpeg, modest concurrency for the AI API steps. Within a job, the rank-aware steps split their files across MPI ranks.

The job scripts are set up for **UNI's HPC cluster** (partition `defq`, Python environment in `/data/<catID>/pve`, no memory or GPU requests). For another cluster, see [Other clusters](#other-clusters).

```
cluster/
├── config.example.yaml        # template; copy to config.yaml
├── config-gold-standard.yaml  # fuller example inspired by AI-SummarizeVid
├── cluster_env.sh             # partition / memory / GPU settings for UNI's cluster; loaded by submit_pipeline.sh
├── cluster_env.example.sh     # template for other clusters
└── slurm/
    ├── common_env.sh              # module loads, environment activation, API keys — sourced by every job
    ├── submit_pipeline.sh         # submits the whole chain
    ├── 01_transcribe.slurm        # 2 nodes x 1 task (GPU only when USE_GPU=1)
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

## 1. Set up the environment (once)

Clone this repository into your HPC directory, then, on a login node, create the Python environment that `common_env.sh` activates (`/data/<catID>/pve`), built against the cluster's MPI:

```bash
export TMPDIR="/home/$USER/data/tmp"
mkdir -p $TMPDIR
module load python3.11 openmpi/gcc/64/4.1.8
python -m venv /data/$USER/pve
/data/$USER/pve/bin/pip install -r requirements.txt mpi4py
```

ffmpeg is already installed at `/usr/bin/ffmpeg`, so it needs no module.

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
- Set `transcription.device: "cpu"`. On UNI's cluster transcription runs on `defq` without a GPU (`USE_GPU=0` in `cluster_env.sh`). If you turn on `USE_GPU=1` on a cluster with Slurm-visible GPUs, set it to `"cuda"`.
- Set `enabled: true` on the steps you want. Disabled steps exit immediately inside their job without failing the chain; use `SKIP_STEPS` to avoid queueing them at all.
- Relative paths are resolved against the config file's folder (`cluster/`).

## 3. Cluster settings

`submit_pipeline.sh` loads `cluster/cluster_env.sh` and adds the matching `--partition`, `--mem` and `--gres` flags to every job, so the `#SBATCH --partition` lines in the `.slurm` files are only placeholders. For UNI it sets:

| Setting | UNI value | Why |
|---|---|---|
| `CPU_PARTITION` | `defq` | Partition for every stage |
| `CPU_MEM`, `GPU_MEM` | empty | The cluster doesn't track memory (`RealMemory=1`), so any `--mem` request is rejected |
| `USE_GPU` | `0` | The `gpuq` nodes don't register GPUs with Slurm (`Gres=(null)`), so transcription runs on `defq` |

Values set on the command line win, e.g. `CPU_MEM=32G cluster/slurm/submit_pipeline.sh`. Each submitted `sbatch` command is printed so you can check the flags.

`--nodes` / `--ntasks-per-node` per stage are starting points. Turn the AI steps down if you hit API rate limits; size up `keyframes` and `describe_frames` for large collections. `--time` is set per stage in the `.slurm` files.

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

## Other clusters

1. Copy `cluster/cluster_env.example.sh` over `cluster/cluster_env.sh` and fill in your partitions, memory and GPU request (from `sinfo -s` and `sinfo -o "%P %D %c %m %G"`).
2. Edit the `module load` lines and the environment activation in `cluster/slurm/common_env.sh`.
3. If your cluster has Slurm-visible GPUs, set `USE_GPU=1` and `transcription.device: "cuda"`.

See [../pipeline/README.md](../pipeline/README.md) for the full configuration reference.

#!/bin/bash
#===============================================================================
# submit_pipeline.sh
#
# Submits every pipeline stage as its own SLURM job, chained with
# --dependency=afterok so each stage only starts once the previous one has
# succeeded. Each stage script requests its own resources (GPU for
# transcription, wide CPU fan-out for keyframes/ffmpeg, modest concurrency
# for the AI API steps), so you can tune them independently instead of
# sizing one job for the whole workflow.
#
# Usage (from anywhere):
#   cluster/slurm/submit_pipeline.sh [path/to/config.yaml]     # default: cluster/config.yaml
#
# Skip stages (e.g. you already have transcripts and keyframes):
#   SKIP_STEPS="transcribe keyframes" cluster/slurm/submit_pipeline.sh
#
# Run only a subset:
#   ONLY_STEPS="describe_frames summarize" cluster/slurm/submit_pipeline.sh
#
# Steps disabled in the config are skipped by run_pipeline.py inside the job,
# so their jobs finish in seconds; use SKIP_STEPS to avoid queueing them.
#
# Partitions, memory and GPUs: the .slurm files only carry placeholder
# partitions and request no --mem or --gres. This script loads
# cluster/cluster_env.sh (set up for UNI's cluster) and adds the matching
# sbatch flags to every job. Override any value on the command line:
#   CPU_PARTITION=batch CPU_MEM=32G cluster/slurm/submit_pipeline.sh
#   USE_GPU=1 GPU_PARTITION=gpu GPU_GRES=gpu:1 cluster/slurm/submit_pipeline.sh
#===============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(cd "${CLUSTER_DIR}/.." && pwd)"

CONFIG_ARG="${1:-${CLUSTER_DIR}/config.yaml}"
if [[ ! -f "${CONFIG_ARG}" ]]; then
    echo "Config not found: ${CONFIG_ARG}" >&2
    echo "Create one with: cp ${CLUSTER_DIR}/config.example.yaml ${CLUSTER_DIR}/config.yaml" >&2
    exit 1
fi
# Jobs run with their working directory set to cluster/, so pass an absolute path.
CONFIG="$(cd "$(dirname "${CONFIG_ARG}")" && pwd)/$(basename "${CONFIG_ARG}")"

# sbatch copies each job script to a spool directory, so the jobs cannot find
# their siblings via $0. Export the locations instead (sbatch exports the
# submitting environment by default).
export AV_SLURM_DIR="${SCRIPT_DIR}"
export AV_CLUSTER_DIR="${CLUSTER_DIR}"
export AV_PIPELINE_DIR="${REPO_DIR}/pipeline"

# Cluster resource settings. Command-line values win over cluster_env.sh.
if [[ -f "${CLUSTER_DIR}/cluster_env.sh" ]]; then
    # shellcheck source=/dev/null
    source "${CLUSTER_DIR}/cluster_env.sh"
fi
CPU_PARTITION="${CPU_PARTITION:-}"
GPU_PARTITION="${GPU_PARTITION:-}"
CPU_MEM="${CPU_MEM:-}"
GPU_MEM="${GPU_MEM:-}"
GPU_GRES="${GPU_GRES:-gpu:1}"
USE_GPU="${USE_GPU:-1}"   # 0 = run transcribe on CPU_PARTITION with no --gres

# Ordered list of step_name:script_file:resource_class, matching the step
# order in pipeline/run_pipeline.py. resource_class is "gpu" for the one
# stage that can use a GPU and "cpu" for everything else.
STEPS=(
    "transcribe:01_transcribe.slurm:gpu"
    "keyframes:02_keyframes.slurm:cpu"
    "describe_frames:03_describe_frames.slurm:cpu"
    "summarize:04_summarize.slurm:cpu"
    "tags:05_tags.slurm:cpu"
    "accessibility:06_accessibility.slurm:cpu"
    "collection_report:07_collection_report.slurm:cpu"
    "preview:08_preview.slurm:cpu"
    "quality_metrics:09_quality_metrics.slurm:cpu"
    "iiif:10_iiif.slurm:cpu"
    "catalog_export:11_catalog_export.slurm:cpu"
    "search_index:12_search_index.slurm:cpu"
    "clustering:13_clustering.slurm:cpu"
)

SKIP_STEPS="${SKIP_STEPS:-}"
ONLY_STEPS="${ONLY_STEPS:-}"

should_run () {
    local step="$1"
    if [[ -n "${ONLY_STEPS}" ]]; then
        [[ " ${ONLY_STEPS} " == *" ${step} "* ]] && return 0 || return 1
    fi
    if [[ -n "${SKIP_STEPS}" ]] && [[ " ${SKIP_STEPS} " == *" ${step} "* ]]; then
        return 1
    fi
    return 0
}

mkdir -p "${CLUSTER_DIR}/logs"

prev_jobid=""
submitted_any=0

for entry in "${STEPS[@]}"; do
    IFS=':' read -r step script resource_class <<< "${entry}"

    if ! should_run "${step}"; then
        echo "Skipping ${step} (${script})"
        continue
    fi

    sbatch_args=(--parsable --chdir="${CLUSTER_DIR}")
    if [[ -n "${prev_jobid}" ]]; then
        sbatch_args+=(--dependency=afterok:"${prev_jobid}")
    fi
    if [[ "${resource_class}" == "gpu" && "${USE_GPU}" != "0" ]]; then
        [[ -n "${GPU_PARTITION}" ]] && sbatch_args+=(--partition="${GPU_PARTITION}")
        [[ -n "${GPU_MEM}" ]] && sbatch_args+=(--mem="${GPU_MEM}")
        [[ -n "${GPU_GRES}" ]] && sbatch_args+=(--gres="${GPU_GRES}")
    else
        [[ -n "${CPU_PARTITION}" ]] && sbatch_args+=(--partition="${CPU_PARTITION}")
        [[ -n "${CPU_MEM}" ]] && sbatch_args+=(--mem="${CPU_MEM}")
    fi
    echo "+ sbatch ${sbatch_args[*]} ${script}" >&2
    jobid=$(sbatch "${sbatch_args[@]}" "${SCRIPT_DIR}/${script}" "${CONFIG}")

    echo "Submitted ${step} (${script}) as job ${jobid}$( [[ -n "${prev_jobid}" ]] && echo " (after ${prev_jobid})")"
    prev_jobid="${jobid}"
    submitted_any=1
done

if [[ "${submitted_any}" -eq 0 ]]; then
    echo "No steps submitted — check ONLY_STEPS/SKIP_STEPS." >&2
    exit 1
fi

echo "Final job in chain: ${prev_jobid}"
echo "Logs:                        ${CLUSTER_DIR}/logs/"
echo "Track the whole chain with:  squeue -u \$USER"
echo "Or watch it live with:       watch -n 30 squeue -u \$USER"

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

# Ordered list of (step_name, script_file) pairs, matching the step order in
# pipeline/run_pipeline.py.
STEPS=(
    "transcribe:01_transcribe.slurm"
    "keyframes:02_keyframes.slurm"
    "describe_frames:03_describe_frames.slurm"
    "summarize:04_summarize.slurm"
    "tags:05_tags.slurm"
    "accessibility:06_accessibility.slurm"
    "collection_report:07_collection_report.slurm"
    "preview:08_preview.slurm"
    "quality_metrics:09_quality_metrics.slurm"
    "iiif:10_iiif.slurm"
    "catalog_export:11_catalog_export.slurm"
    "search_index:12_search_index.slurm"
    "clustering:13_clustering.slurm"
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
    step="${entry%%:*}"
    script="${entry##*:}"

    if ! should_run "${step}"; then
        echo "Skipping ${step} (${script})"
        continue
    fi

    sbatch_args=(--parsable --chdir="${CLUSTER_DIR}")
    if [[ -n "${prev_jobid}" ]]; then
        sbatch_args+=(--dependency=afterok:"${prev_jobid}")
    fi
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

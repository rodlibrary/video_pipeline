#!/bin/bash
#===============================================================================
# submit_pipeline.sh
#
# Submits every pipeline stage as its own SLURM job, chained with
# --dependency=afterok so each stage only starts once the previous one has
# succeeded. Each stage script requests its own resources (GPU for
# transcription, wide CPU fan-out for keyframes/ffmpeg, modest concurrency
# for the Gemini API steps), so you can tune them independently instead of
# sizing one job for the whole workflow.
#
# Usage:
#   ./submit_pipeline.sh [config.yaml]
#
# Skip stages (e.g. you already have transcripts and keyframes):
#   SKIP_STEPS="transcribe keyframes" ./submit_pipeline.sh config.yaml
#
# Run only a subset:
#   ONLY_STEPS="describe_frames summarize" ./submit_pipeline.sh config.yaml
#===============================================================================

set -euo pipefail

CONFIG="${1:-config.yaml}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ordered list of (step_name, script_file) pairs — must match run_pipeline.py's
# PIPELINE_CMDS ordering.
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

mkdir -p "${SCRIPT_DIR}/../logs"

prev_jobid=""
submitted_any=0

for entry in "${STEPS[@]}"; do
    step="${entry%%:*}"
    script="${entry##*:}"

    if ! should_run "${step}"; then
        echo "Skipping ${step} (${script})"
        continue
    fi

    if [[ -z "${prev_jobid}" ]]; then
        jobid=$(sbatch --parsable "${SCRIPT_DIR}/${script}" "${CONFIG}")
    else
        jobid=$(sbatch --parsable --dependency=afterok:"${prev_jobid}" "${SCRIPT_DIR}/${script}" "${CONFIG}")
    fi

    echo "Submitted ${step} (${script}) as job ${jobid}$( [[ -n "${prev_jobid}" ]] && echo " (after ${prev_jobid})")"
    prev_jobid="${jobid}"
    submitted_any=1
done

if [[ "${submitted_any}" -eq 0 ]]; then
    echo "No steps submitted — check ONLY_STEPS/SKIP_STEPS." >&2
    exit 1
fi

echo "Final job in chain: ${prev_jobid}"
echo "Track the whole chain with: squeue -u \$USER"
echo "Or watch it live with:      watch -n 30 squeue -u \$USER"

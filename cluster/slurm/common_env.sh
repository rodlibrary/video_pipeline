#!/bin/bash
#===============================================================================
# common_env.sh
#
# Sourced (not executed) by every stage script in this directory. Keeps
# module loads, environment activation, and credential handling in one
# place instead of thirteen. The module names and environment path below
# are set for UNI's HPC cluster; adjust them for other clusters.
#
# Expects these variables, which submit_pipeline.sh exports for every job:
#   AV_PIPELINE_DIR  absolute path to the repository's pipeline/ folder
#   AV_CLUSTER_DIR   absolute path to the repository's cluster/ folder
#===============================================================================

set -euo pipefail

: "${AV_PIPELINE_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}"
: "${AV_CLUSTER_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}"

module purge
module load openmpi/gcc/64/4.1.8  # UNI: confirmed via `module avail openmpi`
# UNI: ffmpeg is at /usr/bin/ffmpeg (already on PATH), so no module is needed.
# UNI: there is no conda/miniconda module, so activate the venv directly.
# Other clusters: e.g. `module load ffmpeg/6.0 miniconda3` and `source activate av-toolkit`.

source "/data/${USER}/pve/bin/activate"

# --- API credentials ---------------------------------------------------------
# Never hardcode secrets. Store keys in files only you can read (chmod 600).
# Which variable a step uses is set by `api_key_env` in its config section
# (default OPENAI_API_KEY; use GOOGLE_API_KEY with Gemini's OpenAI-compatible
# endpoint). Steps that need no API, such as transcribe and keyframes, run
# without any key; run_pipeline.py reports a missing key for the steps that do.
if [[ -f "${HOME}/.secrets/openai_api_key" ]]; then
    OPENAI_API_KEY="$(cat "${HOME}/.secrets/openai_api_key")"
    export OPENAI_API_KEY
fi
if [[ -f "${HOME}/.secrets/google_api_key" ]]; then
    GOOGLE_API_KEY="$(cat "${HOME}/.secrets/google_api_key")"
    export GOOGLE_API_KEY
fi

cd "${AV_CLUSTER_DIR}"
mkdir -p logs

CONFIG="${1:-${AV_CLUSTER_DIR}/config.yaml}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
PIPELINE="${AV_PIPELINE_DIR}/run_pipeline.py"

echo "=== ${SLURM_JOB_NAME:-$(basename "$0")} starting: $(date) ==="
echo "Config file:  ${CONFIG}"
echo "Job ID:       ${SLURM_JOB_ID:-n/a}"
echo "Nodes/tasks:  ${SLURM_NNODES:-1} nodes x ${SLURM_NTASKS_PER_NODE:-1} tasks/node = ${SLURM_NTASKS:-1} ranks"
echo "Threads/rank: ${OMP_NUM_THREADS}"

#!/bin/bash
#SBATCH --job-name=av-02-keyframes
#SBATCH --partition=compute
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=16                # ffmpeg is cheap per-frame; scale out on CPU
#SBATCH --cpus-per-task=2
#SBATCH --time=04:00:00
#SBATCH --output=logs/02-keyframes-%j.out
#SBATCH --error=logs/02-keyframes-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

python "${PIPELINE}" --config "${CONFIG}" --ranks "${SLURM_NTASKS}" --steps keyframes

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

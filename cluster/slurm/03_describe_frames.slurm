#!/bin/bash
#SBATCH --job-name=av-03-describe-frames
#SBATCH --partition=compute
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4                 # AI vision API calls: keep concurrency modest, tune to your quota
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --output=logs/03-describe-frames-%j.out
#SBATCH --error=logs/03-describe-frames-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

python "${PIPELINE}" --config "${CONFIG}" --ranks "${SLURM_NTASKS}" --steps describe_frames

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

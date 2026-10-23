#!/bin/bash
#SBATCH --job-name=av-06-accessibility
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8                 # AI text API calls: tune to your quota
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=03:00:00
#SBATCH --output=logs/06-accessibility-%j.out
#SBATCH --error=logs/06-accessibility-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

python "${PIPELINE}" --config "${CONFIG}" --ranks "${SLURM_NTASKS}" --steps accessibility

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

#!/bin/bash
#SBATCH --job-name=av-08-preview
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1                          # not rank-aware; must run as a single process
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00
#SBATCH --output=logs/08-preview-%j.out
#SBATCH --error=logs/08-preview-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

# Builds the static HTML dashboard; no external API calls.
python "${PIPELINE}" --config "${CONFIG}" --no-mpi --steps preview

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

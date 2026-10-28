#!/bin/bash
#SBATCH --job-name=av-07-collection_report
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1                          # not rank-aware; must run as a single process
#SBATCH --cpus-per-task=2
#SBATCH --time=01:00:00
#SBATCH --output=logs/07-collection_report-%j.out
#SBATCH --error=logs/07-collection_report-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

# Calls the AI API once for the whole collection.
python "${PIPELINE}" --config "${CONFIG}" --no-mpi --steps collection_report

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

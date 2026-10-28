#!/bin/bash
#SBATCH --job-name=av-09-quality_metrics
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1                          # not rank-aware; must run as a single process
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00
#SBATCH --output=logs/09-quality_metrics-%j.out
#SBATCH --error=logs/09-quality_metrics-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

# Heuristic QA metrics; no external API calls.
python "${PIPELINE}" --config "${CONFIG}" --no-mpi --steps quality_metrics

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

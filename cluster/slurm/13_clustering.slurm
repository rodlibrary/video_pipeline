#!/bin/bash
#SBATCH --job-name=av-13-clustering
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1                          # not rank-aware; must run as a single process
#SBATCH --cpus-per-task=2
#SBATCH --time=02:00:00
#SBATCH --output=logs/13-clustering-%j.out
#SBATCH --error=logs/13-clustering-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

# Calls the AI embeddings API in batches, then runs k-means locally.
python "${PIPELINE}" --config "${CONFIG}" --no-mpi --steps clustering

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

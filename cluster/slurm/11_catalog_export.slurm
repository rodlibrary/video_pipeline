#!/bin/bash
#SBATCH --job-name=av-11-catalog_export
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1                          # not rank-aware; must run as a single process
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --output=logs/11-catalog_export-%j.out
#SBATCH --error=logs/11-catalog_export-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

# CSV export; no external API calls.
python "${PIPELINE}" --config "${CONFIG}" --no-mpi --steps catalog_export

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

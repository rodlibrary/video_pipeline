#!/bin/bash
#SBATCH --job-name=av-01-transcribe
#SBATCH --partition=gpu                     # <-- GPU partition; Whisper large-v3 wants a GPU
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1                 # one Whisper model instance per GPU
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/01-transcribe-%j.out
#SBATCH --error=logs/01-transcribe-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

# NOTE: set transcription.device: "cuda" in your config to actually use the GPU.
python "${PIPELINE}" --config "${CONFIG}" --ranks "${SLURM_NTASKS}" --steps transcribe

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

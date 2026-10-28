#!/bin/bash
#SBATCH --job-name=av-01-transcribe
#SBATCH --partition=gpu                     # placeholder; submit_pipeline.sh applies GPU_PARTITION/CPU_PARTITION from cluster_env.sh
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1                 # one Whisper model instance per GPU
#SBATCH --cpus-per-task=8
#SBATCH --time=06:00:00
#SBATCH --output=logs/01-transcribe-%j.out
#SBATCH --error=logs/01-transcribe-%j.err

source "${AV_SLURM_DIR:?Submit jobs with cluster/slurm/submit_pipeline.sh}/common_env.sh" "$@"

# NOTE: with USE_GPU=1, set transcription.device: "cuda" in your config to use the GPU.
# With USE_GPU=0 (UNI default), set it to "cpu".
python "${PIPELINE}" --config "${CONFIG}" --ranks "${SLURM_NTASKS}" --steps transcribe

echo "=== ${SLURM_JOB_NAME} finished: $(date) ==="

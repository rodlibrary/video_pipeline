#!/bin/bash
#===============================================================================
# cluster_env.sh — SLURM resource settings for UNI's HPC cluster (defq / gpuq)
#
# submit_pipeline.sh loads this file automatically. Values you set on the
# command line win, e.g.:  USE_GPU=1 cluster/slurm/submit_pipeline.sh
#
# UNI's cluster does not track memory as a schedulable Slurm resource (every
# node reports RealMemory=1), and the gpuq nodes don't register GPUs as a
# Slurm generic resource (Gres=(null)). So no --mem is requested and
# USE_GPU=0: transcription runs on defq like every other stage, with no
# --gres request. Set transcription.device: "cpu" in config.yaml to match.
#
# For another cluster, copy cluster_env.example.sh over this file and fill in
# values from `sinfo -s` and `sinfo -o "%P %D %c %m %G"`.
#===============================================================================

export CPU_PARTITION="${CPU_PARTITION:-defq}"
export GPU_PARTITION="${GPU_PARTITION:-gpuq}"   # only used when USE_GPU=1
export CPU_MEM="${CPU_MEM:-}"                   # intentionally empty, see above
export GPU_MEM="${GPU_MEM:-}"                   # intentionally empty, see above
export USE_GPU="${USE_GPU:-0}"                  # gpuq has no Slurm-visible GPUs

echo "Loaded cluster settings: partition=${CPU_PARTITION}, USE_GPU=${USE_GPU}, mem=${CPU_MEM:-none}"

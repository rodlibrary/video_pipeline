#!/bin/bash
#===============================================================================
# cluster_env.example.sh — template for clusters other than UNI's
#
# Copy this over cluster/cluster_env.sh and fill in your cluster's values
# (from `sinfo -s` and `sinfo -o "%P %D %c %m %G"`). submit_pipeline.sh
# loads cluster_env.sh automatically; values set on the command line win.
#===============================================================================

export CPU_PARTITION="${CPU_PARTITION:-batch}"  # your CPU partition
export GPU_PARTITION="${GPU_PARTITION:-gpu}"    # your GPU partition (used when USE_GPU=1)
export CPU_MEM="${CPU_MEM:-32G}"                # must fit your smallest CPU node; keyframes is the heaviest CPU stage
export GPU_MEM="${GPU_MEM:-48G}"                # must fit your GPU node
export GPU_GRES="${GPU_GRES:-gpu:1}"            # GPU request for transcribe when USE_GPU=1
export USE_GPU="${USE_GPU:-1}"                  # 0 if your cluster has no Slurm-visible GPUs

echo "Loaded cluster settings: partition=${CPU_PARTITION}/${GPU_PARTITION}, mem=${CPU_MEM}/${GPU_MEM}, USE_GPU=${USE_GPU}"

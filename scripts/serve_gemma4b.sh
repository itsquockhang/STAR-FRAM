docker run -itd --name gemma4-E2B \
    --ipc=host \
    --network host \
    --shm-size 16G \
    --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    vllm/vllm-openai:gemma4-cu130 \
        --model google/gemma-4-E2B-it \
        --tensor-parallel-size 1 \
        --max-model-len 16384 \
        --gpu-memory-utilization 0.8 \
        --host 0.0.0.0 \
        --port 8129
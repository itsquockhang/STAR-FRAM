docker run -itd --name gemma-4-E2B-it-qat-w4a16-ct \
    --ipc=host \
    --network host \
    --shm-size 16G \
    --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    vllm/vllm-openai:gemma4-cu130 \
        --model google/gemma-4-E2B-it-qat-w4a16-ct \
        --language-model-only \
        --reasoning-parser gemma4 \
        --tool-call-parser gemma4 \
        --distributed-executor-backend mp \
        --max-num-seqs 8 \
        --max-model-len 16384 \
        --gpu-memory-utilization 0.85 \
        --host 0.0.0.0 \
        --port 8129
# curl http://127.0.0.1:8129/v1/chat/completions   -H "Content-Type: application/json"   -d '{
#     "model": "google/gemma-4-E2B-it-qat-w4a16-ct",
#     "messages": [
#       {"role": "system", "content": "Bạn là một trợ lý AI hữu ích."},
#       {"role": "user", "content": "Xin chào! Bạn có thể giới thiệu ngắn gọn về bản thân không?"}
#     ],
#     "temperature": 0.7
#   }'

## Tested on RTX 3060 12GB VRAM

docker run -itd --name gemma-4-E2B-it-qat-w4a16-ct \
    --ipc=host \
    --network host \
    --shm-size 16G \
    --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    vllm/vllm-openai:gemma4-cu130 \
        google/gemma-4-E2B-it-qat-w4a16-ct \
        --language-model-only \
        --reasoning-parser gemma4 \
        --max-num-seqs 2 \
        --max-model-len 2048 \
        --gpu-memory-utilization 0.92 \
        --max-num-batched-tokens 2048 \
        --enforce-eager \
        --swap-space 4 \
        --host 0.0.0.0 \
        --port 8129
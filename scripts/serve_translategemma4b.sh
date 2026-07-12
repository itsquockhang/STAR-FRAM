# docker pull vllm/vllm-openai:v0.14.1-cu130

# curl -X POST http://localhost:8128/v1/chat/completions \
#   -H "Content-Type: application/json" \
#   -d '{
#     "model": "translategemma-4b-it",
#     "messages": [
#         {
#           "role": "user",
#           "content": "<<<source>>>en<<<target>>>zh<<<text>>>We distribute two models for language identification, which can recognize 176 languages."
#         }
#       ]
#     }'

## Tested on RTX 3060 12GB VRAM

docker run -itd --name google-translategemma-4b-it \
    --ipc=host \
    --network host \
    --shm-size 16G \
    --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    vllm/vllm-openai:v0.14.1-cu130 \
        ViralityLeo/vllm-translategemma-4b-it-FP8-Dynamic \
        --served-model-name translategemma-4b-it \
        --host 0.0.0.0 \
        --port 8128 \
        --max-model-len 4096 \
        --swap-space 4 \
        --gpu-memory-utilization 0.75
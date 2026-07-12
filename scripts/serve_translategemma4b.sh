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

docker run -itd --name google-translategemma-4b-it \
    --ipc=host \
    --network host \
    --shm-size 16G \
    --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    vllm/vllm-openai:v0.14.1-cu130 \
        Infomaniak-AI/vllm-translategemma-4b-it \
        --served-model-name translategemma-4b-it \
        --gpu-memory-utilization 0.8 \
        --host 0.0.0.0 \
        --port 8128
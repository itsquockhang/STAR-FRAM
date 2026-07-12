# docker pull vllm/vllm-openai:v0.14.1-cu130

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
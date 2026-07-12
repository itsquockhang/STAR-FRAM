import logging
import torch

logger = logging.getLogger("starfarm.utils")


def get_device() -> torch.device:
    """Detect the best available compute device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info(f"Using CUDA device: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("Using Apple MPS (Metal Performance Shaders) device.")
    else:
        device = torch.device("cpu")
        logger.info("Using CPU device.")
    return device

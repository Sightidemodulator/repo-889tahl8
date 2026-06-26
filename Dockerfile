FROM python:3.11-slim

# Mirror-aware build args. Defaults use the public indexes; override on networks
# that cannot reach them (e.g. via --build-arg PIP_INDEX=... HF_ENDPOINT=...).
ARG PIP_INDEX=https://pypi.org/simple
ARG TORCH_WHEEL=torch --extra-index-url https://download.pytorch.org/whl/cpu
ARG HF_ENDPOINT=https://huggingface.co
ARG DEBIAN_MIRROR=deb.debian.org

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    HF_ENDPOINT=${HF_ENDPOINT}

WORKDIR /app

# Swap the Debian apt mirror when the default (deb.debian.org) is slow/unreachable,
# e.g. --build-arg DEBIAN_MIRROR=mirrors.tuna.tsinghua.edu.cn
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
 && apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (much smaller than the default CUDA build),
# then the remaining requirements (sentence-transformers reuses this torch).
# TORCH_WHEEL may be a package spec or a direct wheel URL (for a faster mirror),
# e.g. --build-arg TORCH_WHEEL=https://mirrors.aliyun.com/pytorch-wheels/cpu/torch-2.6.0%2Bcpu-cp311-cp311-linux_x86_64.whl
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX} ${TORCH_WHEEL} \
 && pip install --no-cache-dir -i ${PIP_INDEX} -r requirements.txt

# Bake the embedding model into the image so the runtime server needs no
# HuggingFace network access (the target server cannot reach huggingface.co).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

# Application code. data/ is bind-mounted at runtime (persists KB + learning).
COPY src ./src
COPY web ./web

ENV TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1

EXPOSE 7860
CMD ["python", "src/server.py"]

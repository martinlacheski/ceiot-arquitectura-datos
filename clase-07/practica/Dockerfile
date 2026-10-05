FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./
# Keep the local embedding runtime CPU-only. Installing this official wheel
# first prevents sentence-transformers from resolving PyTorch's CUDA packages.
# BAAI/bge-m3 only ships .bin (pickle) weights; transformers refuses to load
# them below torch 2.6 (CVE-2025-32434), so this practice is pinned to 2.6.0.
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.6.0+cpu" \
    && pip install --no-cache-dir --requirement requirements.txt

COPY api ./api
COPY loader ./loader
COPY shared ./shared

ENTRYPOINT ["python", "-m", "loader.seed_services"]
CMD ["--source", "/data/manual-content.json"]

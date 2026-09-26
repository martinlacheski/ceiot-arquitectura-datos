FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./
# Keep the local E5 embedding runtime CPU-only. Installing this official wheel
# first prevents sentence-transformers from resolving PyTorch's CUDA packages.
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.5.1+cpu" \
    && pip install --no-cache-dir --requirement requirements.txt

COPY api ./api
COPY loader ./loader
COPY shared ./shared

ENTRYPOINT ["python", "-m", "loader.seed_services"]
CMD ["--source", "/data/manual-content.json"]

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY config ./config
RUN useradd --system --create-home agente && mkdir -p /app/data && chown -R agente /app
USER agente

HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
  CMD python -c "import os,time,sys; p='/app/data/heartbeat'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 600 else 1)"

CMD ["agente-email"]

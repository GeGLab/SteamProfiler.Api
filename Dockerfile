FROM python:3.13-alpine

LABEL org.opencontainers.image.source="https://github.com/GustavoHSCruz/SteamProfiler.Api" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DATA_DIR=/app/data

WORKDIR /app

# Shareable comparison cards need Unicode typography and bounded JPEG/PNG decoding.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN addgroup -S steamprofiler \
    && adduser -S -G steamprofiler -u 10001 steamprofiler \
    && mkdir -p /app/data \
    && chown steamprofiler:steamprofiler /app/data

COPY --chown=steamprofiler:steamprofiler . /app

USER steamprofiler
EXPOSE 8000

CMD ["python", "/app/api.py"]

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libiio0 libiio-utils ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app
COPY rootfs /
RUN chmod +x /etc/services.d/sdr-recorder/run /etc/services.d/sdr-recorder/finish

WORKDIR /app
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8099/health || exit 1

ENTRYPOINT ["/etc/services.d/sdr-recorder/run"]

# Ingegnere F1: immagine amd64, Python + Piper (voce locale), niente GPU.
# 1) un video nero muto di pochi KB: tiene acceso lo schermo del cellulare senza HTTPS
FROM debian:trixie-slim AS video
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN ffmpeg -loglevel error -f lavfi -i color=c=black:s=32x32:r=5:d=6 -c:v libx264 -pix_fmt yuv420p \
      -movflags +faststart /sveglia.mp4 && \
    ffmpeg -loglevel error -f lavfi -i color=c=black:s=32x32:r=5:d=6 -c:v libvpx -b:v 20k /sveglia.webm

# 2) il servizio
FROM python:3.12-slim
# ORT_DISABLE_TELEMETRY: onnxruntime (usato da Piper) altrimenti manda telemetria a Microsoft
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ORT_DISABLE_TELEMETRY=1 \
    DATI=/dati VOCI=/voci WEB=/web PORTA_UDP=20777 PORTA_WEB=8777 TZ=UTC
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY app /app
COPY web /web
COPY --from=video /sveglia.mp4 /sveglia.webm /web/
WORKDIR /app
USER 1000:1000
EXPOSE 20777/udp 8777/tcp
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8777/api/stato', timeout=4)"
CMD ["python", "-m", "ingegnere.server"]

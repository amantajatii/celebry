FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-ml.txt
COPY --chown=app:app app ./app
COPY --chown=app:app logging.json ./logging.json
COPY --chown=app:app models ./models
COPY --chown=app:app data/celebrities.npz ./data/celebrities.npz
USER app
ENV CELEBRY_DETECTION_MODEL=/app/models/buffalo_s/det_500m.onnx \
    CELEBRY_RECOGNITION_MODEL=/app/models/buffalo_s/w600k_mbf.onnx \
    CELEBRY_CATALOG=/app/data/celebrities.npz CELEBRY_REQUIRE_READY=true \
    CELEBRY_INFERENCE_THREADS=2
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "32", "--timeout-keep-alive", "5", "--timeout-graceful-shutdown", "30", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log", "--log-config", "logging.json"]

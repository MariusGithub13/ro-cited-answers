# The live demo. Standard library only; the model runs behind an
# OpenAI-compatible API, never inside this container.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 RO_BACKEND=openai RO_AUDIT=/data/audit.jsonl
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
WORKDIR /app
COPY ask.py gate_a.json .embeddings*.json ./
COPY corpus ./corpus
COPY web ./web
RUN useradd --uid 10001 --no-create-home app && mkdir -p /data && chown app /data
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=4).status==200 else 1)"
CMD ["python3", "web/app.py"]

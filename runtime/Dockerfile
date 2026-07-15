# AlphaSoft AI Studio runtime — FastAPI orchestrator.
# Runs internal to the platform; Laravel is the only intended caller.
# Never bake .env files or API keys into this image — all secrets arrive
# as environment variables at run time.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install production dependencies only (requirements-dev.txt is tests-only).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the application package. .env, .venv, tests, and caches are
# excluded via .dockerignore and are never copied.
COPY app ./app

# Run as a non-root user.
RUN useradd --create-home --uid 10001 runtime \
    && chown -R runtime:runtime /app
USER runtime

EXPOSE 8100

# Python-stdlib healthcheck — the slim image ships no curl/wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/api/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]

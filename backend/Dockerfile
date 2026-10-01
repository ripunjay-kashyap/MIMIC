# Container image for any Docker host (production uses modal_app.py). Playwright tag MUST match requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ENV PYTHONUNBUFFERED=1 \
    IN_CONTAINER=1 \
    PORT=7860 \
    HOME=/tmp

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app ./app
COPY demo_site ./demo_site
RUN chmod -R a+rX /app

# HF Spaces runs containers as UID 1000; keep the image UID-agnostic (HOME=/tmp is writable).
USER 1000
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

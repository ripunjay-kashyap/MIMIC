# Hugging Face Space (Docker SDK). Playwright image tag MUST match playwright in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ENV PYTHONUNBUFFERED=1 \
    IN_CONTAINER=1 \
    PORT=7860 \
    HOME=/home/pwuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY --chown=pwuser:pwuser app ./app
COPY --chown=pwuser:pwuser demo_site ./demo_site

# HF Spaces runs containers as UID 1000 (pwuser in this image).
USER pwuser
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

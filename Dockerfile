FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[api]"

# SQLite DB lives here — mount a PVC to /data
WORKDIR /data

EXPOSE 8000

CMD ["uvicorn", "wodplanner.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

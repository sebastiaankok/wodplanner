FROM python:3.14-slim

WORKDIR /app
COPY pyproject.toml .

# Stub package so pip can resolve deps without real source
RUN mkdir -p src/wodplanner && touch src/wodplanner/__init__.py
RUN pip install --no-cache-dir -e ".[api]"

# Real source overwrites stub; editable install points here
COPY src/ src/

# SQLite DB lives here — mount a PVC to /data
WORKDIR /data

EXPOSE 8000

CMD ["uvicorn", "wodplanner.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

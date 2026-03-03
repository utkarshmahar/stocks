FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
COPY services/risk-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/risk-engine/main.py .

ENV PYTHONUNBUFFERED=1

EXPOSE 8050
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8050"]

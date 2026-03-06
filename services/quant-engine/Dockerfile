FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
COPY services/quant-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/quant-engine/main.py .
COPY services/quant-engine/scheduler.py .
COPY services/quant-engine/computations/ /app/computations/
COPY services/quant-engine/strategies/ /app/strategies/

ENV PYTHONUNBUFFERED=1

EXPOSE 8020
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]

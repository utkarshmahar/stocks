FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY shared/ /app/shared/
COPY services/options-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/options-agent/main.py .

ENV PYTHONUNBUFFERED=1

EXPOSE 8030
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]

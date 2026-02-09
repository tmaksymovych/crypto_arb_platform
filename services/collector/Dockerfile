FROM python:3.12-slim

WORKDIR /app

# Устанавливаем системные зависимости для сборки бинарных библиотек
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/collector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY services/collector/src/ ./src/

ENV PYTHONPATH=/app

CMD ["python", "src/main.py"]
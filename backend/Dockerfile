FROM python:3.12-slim

WORKDIR /app

# curl нужен для healthcheck в docker-compose
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python-зависимости устанавливаем до копирования кода —
# слой кэшируется и не пересобирается при изменении исходников
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright: --with-deps скачивает Chromium и устанавливает все системные
# зависимости через apt-get за один шаг (нет проблемы с удалёнными apt-списками)
RUN playwright install --with-deps chromium

# Исходный код
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-alpine

WORKDIR /app

# Установка Nginx и Certbot
RUN apk add --no-cache nginx certbot certbot-nginx

RUN pip install poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-interaction --no-ansi

COPY . .

ENV PYTHONPATH=/app

# Монтируем директорию для логов
VOLUME ["/app/logs"]

# Копирование конфигурации Nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Открытие портов 80 и 443 для HTTP и HTTPS
EXPOSE 80 443

# Команда для запуска Nginx и приложения
CMD ["sh", "-c", "nginx && uvicorn main:app --host 0.0.0.0 --port 8000"]

FROM python:3.12-alpine

WORKDIR /app

RUN pip install poetry==1.8.2
RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi --only main

COPY . .

ENV PYTHONPATH=/app

# Монтируем директорию для логов
VOLUME ["/app/logs"]

# Открываем порт 8000
EXPOSE 8000

# Команда для запуска приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Используем легкий образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости (они у тебя должны быть в корне или в папках сервисов)
# Если ты делал pip freeze, файл requirements.txt должен быть в корне
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Устанавливаем переменную окружения для импортов
ENV PYTHONPATH=/app

# Команда по умолчанию будет переопределена в docker-compose.yaml
CMD ["python3"]

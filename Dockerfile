# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все остальные файлы проекта
COPY . .

# Открываем порт, который будет слушать приложение
EXPOSE 8080

# Команда для запуска приложения
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]

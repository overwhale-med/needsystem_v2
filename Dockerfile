# Use official Python 3.11 slim base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files & enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install basic system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    sqlite3 \
    gcc \
    curl \
    unzip \
    && rm -rf /var/lib/apt-lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all project code
COPY . /app/

EXPOSE 8000

# YOLO Mode Command: Auto-migrate & Auto-collectstatic then start Gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput || true && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"]

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y gcc libpq-dev netcat-traditional && rm -rf /var/lib/apt/lists/*

# Copy requirements from the root context
COPY constraints.txt ./constraints.txt
COPY auth-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Copy shared utilities to root so sys.path.append(ROOT_DIR.parent) works
COPY shared /shared

# Copy the actual microservice code
COPY auth-service /app

EXPOSE 8000

# Run migrations, collect static files, then start the server
CMD python manage.py migrate --noinput && \
    python manage.py collectstatic --noinput && \
    gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}

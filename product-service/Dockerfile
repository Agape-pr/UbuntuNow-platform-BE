FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y gcc libpq-dev netcat-traditional && rm -rf /var/lib/apt/lists/*

# Copy requirements from the root context
COPY product-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities to root so sys.path.append(ROOT_DIR.parent) works
COPY shared /shared

# Copy the actual microservice code
COPY product-service /app

EXPOSE 8000

CMD python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --bind [::]:${PORT:-8000}

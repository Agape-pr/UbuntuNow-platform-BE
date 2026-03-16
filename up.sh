#!/bin/bash
set -e

echo "Injecting shared core utilities into microservices..."
for svc in auth store product order payment notification; do
  # Remove old core to ensure clean injection
  rm -rf $svc-service/core
  # Copy the shared core into the service
  cp -R shared/core $svc-service/
done

echo "Starting Real Microservices Cluster..."
docker-compose up --build -d

echo ""
echo "==========================================="
echo "✅ Architecture Deployed Successfully!"
echo "API Gateway : http://localhost:8000"
echo "RabbitMQ UI : http://localhost:15672 (guest/guest)"
echo "PostgreSQL  : localhost:5432 (6 Isolated DBs)"
echo "==========================================="

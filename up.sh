#!/bin/bash
set -e

echo "Starting Real Microservices Cluster..."
docker-compose up --build -d

echo ""
echo "==========================================="
echo "✅ Architecture Deployed Successfully!"
echo "API Gateway : http://localhost:8000"
echo "RabbitMQ UI : http://localhost:15672 (guest/guest)"
echo "PostgreSQL  : localhost:5432 (6 Isolated DBs)"
echo "==========================================="

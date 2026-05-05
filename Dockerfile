# serverless/Dockerfile

# Base image
FROM python:3.13.5-slim AS base

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .
EXPOSE 8000
CMD ["python", "main.py", "-u"]
# docker build -t runpod-serverless-local:latest -f Dockerfile .
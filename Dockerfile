FROM node:18-slim as frontend-base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.11-slim

# Install system dependencies + Node.js
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Create vscode user
RUN useradd -m -s /bin/bash vscode
USER vscode

WORKDIR /workspace

# Keep container running
CMD ["sleep", "infinity"]
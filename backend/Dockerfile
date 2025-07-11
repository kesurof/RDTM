# Multi-stage build pour optimiser la taille
FROM python:3.11-slim as builder

WORKDIR /app

# Installation des dépendances système
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage de production
FROM python:3.11-slim

WORKDIR /app

# Création d'un utilisateur non-root
RUN useradd --create-home --shell /bin/bash app

# Copie des dépendances depuis le builder
COPY --from=builder /root/.local /home/app/.local

# Copie du code source
COPY --chown=app:app . .

# Configuration de l'environnement
ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONPATH=/app/src

USER app

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

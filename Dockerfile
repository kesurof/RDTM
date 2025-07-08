# Dockerfile
FROM python:3.11-slim

# Métadonnées
LABEL maintainer="Real-Debrid Manager"
LABEL description="Gestionnaire automatique de torrents Real-Debrid"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Créer utilisateur non-root
RUN groupadd -r rdmanager && useradd -r -g rdmanager rdmanager

# Répertoire de travail
WORKDIR /app

# Copier les dépendances et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY --chown=rdmanager:rdmanager . .

# Créer les répertoires nécessaires
RUN mkdir -p /app/logs /app/data /app/config && \
    chown -R rdmanager:rdmanager /app

# Passer à l'utilisateur non-root
USER rdmanager

# Point d'entrée
CMD ["python", "main.py"]

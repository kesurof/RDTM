#!/usr/bin/env python3
"""
Script de génération de secrets sécurisés pour RDTM
"""

import secrets
import string
import os
from cryptography.fernet import Fernet

def generate_secret_key(length=64):
    """Génère une clé secrète aléatoire"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_jwt_secret():
    """Génère un secret JWT"""
    return secrets.token_urlsafe(64)

def generate_encryption_key():
    """Génère une clé de chiffrement Fernet"""
    return Fernet.generate_key().decode()

def generate_password(length=32):
    """Génère un mot de passe sécurisé"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def main():
    """Génère tous les secrets nécessaires"""
    secrets_config = {
        'SECRET_KEY': generate_secret_key(),
        'JWT_SECRET': generate_jwt_secret(),
        'ENCRYPTION_KEY': generate_encryption_key(),
        'DB_PASSWORD': generate_password(),
        'GRAFANA_ADMIN_PASSWORD': generate_password(16)
    }
    
    print("# Secrets générés pour RDTM")
    print("# ATTENTION : Stockez ces valeurs de manière sécurisée")
    print("# Ne commitez jamais ce fichier dans le contrôle de version")
    print()
    
    for key, value in secrets_config.items():
        print(f"{key}={value}")
    
    # Sauvegarde optionnelle dans un fichier
    env_file = ".env.local"
    if not os.path.exists(env_file):
        with open(env_file, 'w') as f:
            f.write("# Secrets générés automatiquement\n")
            f.write("# ATTENTION : Ne commitez jamais ce fichier\n\n")
            for key, value in secrets_config.items():
                f.write(f"{key}={value}\n")
        print(f"\nSecrets sauvegardés dans {env_file}")
        print("Ajoutez ce fichier à .gitignore !")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Générateur de secrets cryptographiquement sécurisé pour RDTM
"""
import secrets
import string
import hashlib
import os
import argparse
from pathlib import Path
from cryptography.fernet import Fernet
import base64

class SecureSecretGenerator:
    def __init__(self):
        self.min_length = {
            'secret_key': 64,
            'jwt_secret': 32,
            'db_password': 16,
            'encryption_key': 32
        }
    
    def generate_secret_key(self, length=64):
        """Génère une clé secrète Django sécurisée"""
        chars = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    def generate_jwt_secret(self, length=32):
        """Génère un secret JWT cryptographiquement sécurisé"""
        return secrets.token_urlsafe(length)
    
    def generate_db_password(self, length=16):
        """Génère un mot de passe base de données fort"""
        chars = string.ascii_letters + string.digits + '!@#$%^&*'
        password = ''.join(secrets.choice(chars) for _ in range(length))
        
        # Validation de la force
        if not self._validate_password_strength(password):
            return self.generate_db_password(length)
        return password
    
    def generate_encryption_key(self):
        """Génère une clé de chiffrement Fernet"""
        return Fernet.generate_key().decode()
    
    def _validate_password_strength(self, password):
        """Valide la force d'un mot de passe"""
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*' for c in password)
        
        return all([has_upper, has_lower, has_digit, has_special])
    
    def generate_all_secrets(self):
        """Génère tous les secrets nécessaires"""
        return {
            'DJANGO_SECRET_KEY': self.generate_secret_key(),
            'JWT_SECRET_KEY': self.generate_jwt_secret(),
            'POSTGRES_PASSWORD': self.generate_db_password(),
            'ENCRYPTION_KEY': self.generate_encryption_key(),
            'REDIS_PASSWORD': self.generate_db_password(20),
            'API_RATE_LIMIT_SECRET': self.generate_jwt_secret(16)
        }
    
    def save_to_env_file(self, secrets_dict, filepath='.env'):
        """Sauvegarde les secrets dans un fichier .env"""
        env_content = []
        
        # En-tête de sécurité
        env_content.append("# RDTM Environment Variables")
        env_content.append("# Generated automatically - DO NOT COMMIT TO VERSION CONTROL")
        env_content.append("# Regenerate in production with: python scripts/generate_secure_secrets.py")
        env_content.append("")
        
        # Secrets
        env_content.append("# Security Secrets")
        for key, value in secrets_dict.items():
            env_content.append(f"{key}={value}")
        
        # Configuration par défaut
        env_content.extend([
            "",
            "# Database Configuration",
            "POSTGRES_DB=rdtm",
            "POSTGRES_USER=rdtm_user",
            "POSTGRES_HOST=db",
            "POSTGRES_PORT=5432",
            "",
            "# Redis Configuration",
            "REDIS_HOST=redis",
            "REDIS_PORT=6379",
            "REDIS_DB=0",
            "",
            "# Application Configuration",
            "DEBUG=False",
            "ALLOWED_HOSTS=localhost,127.0.0.1",
            "CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000",
            "",
            "# Real-Debrid Configuration",
            "REAL_DEBRID_API_URL=https://api.real-debrid.com/rest/1.0",
            "REAL_DEBRID_TIMEOUT=30",
            "",
            "# Security Settings",
            "SECURE_SSL_REDIRECT=True",
            "SECURE_HSTS_SECONDS=31536000",
            "SECURE_HSTS_INCLUDE_SUBDOMAINS=True",
            "SECURE_HSTS_PRELOAD=True",
            "SECURE_CONTENT_TYPE_NOSNIFF=True",
            "SECURE_BROWSER_XSS_FILTER=True",
            "SESSION_COOKIE_SECURE=True",
            "CSRF_COOKIE_SECURE=True"
        ])
        
        with open(filepath, 'w') as f:
            f.write('\n'.join(env_content))
        
        # Sécuriser les permissions du fichier
        os.chmod(filepath, 0o600)
        print(f"✅ Secrets générés et sauvegardés dans {filepath}")
        print("⚠️  IMPORTANT: Ne jamais commiter ce fichier dans le contrôle de version!")

def main():
    parser = argparse.ArgumentParser(description='Générateur de secrets sécurisé pour RDTM')
    parser.add_argument('--output', '-o', default='.env', help='Fichier de sortie (défaut: .env)')
    parser.add_argument('--force', '-f', action='store_true', help='Forcer la régénération même si le fichier existe')
    
    args = parser.parse_args()
    
    if Path(args.output).exists() and not args.force:
        print(f"❌ Le fichier {args.output} existe déjà. Utilisez --force pour le remplacer.")
        return
    
    generator = SecureSecretGenerator()
    secrets_dict = generator.generate_all_secrets()
    generator.save_to_env_file(secrets_dict, args.output)

if __name__ == '__main__':
    main()
